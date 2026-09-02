"""
Sequence construction for all components.

Owns the feature engineering / windowing logic that turns one ATM's raw
monetary-server rows into the exact sequence shape each component's
downstream inference model expects.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from sklearn.preprocessing import StandardScaler

from app.config import get_settings


# Module-level constants (configurable via config.py)
settings = get_settings()
MAX_DUR_MINUTES: float = 43200.0  # 30 days * 24h * 60min (lookback_days=30)
MAX_LEN: int = 500
SCALERS_DIR: Path = settings.scalers_path

# Load one-hot encoding categories from training
CATEGORIES_PATH: Path = settings.categories_path
with open(CATEGORIES_PATH) as f:
    CATEGORIES = json.load(f)

# Map JSON keys to DataFrame column names
CATEGORY_COLUMN_MAP = {
    "instit": "INSTITUTION",
    "version": "VERSION",
}


def build_sequence(pid: str, records: list[dict[str, Any]], component: str) -> dict[str, Any]:
    """Build the model-ready sequence for a component for one ATM.

    Input:
        pid: the ATM identifier.
        records: that ATM's raw monetary-server rows for the lookback
            window, sorted ascending by query_date, each shaped like:
            {
                "pid": str, "query_date": iso-datetime, "version": str | None,
                "institution": str | None, "nbre_cas_1": int, "nbre_cas_2": int,
                "nbre3": int, "nbre_cas_4": int, "cmd_cas_1": int | None,
                "cmd_cas_2": int | None, "cmd_cas_3": int | None,
                "cmd_cas_4": int | None, "rece_print": int | None
            }
        component: one of "CMD_CAS_1", "CMD_CAS_2", "CMD_CAS_3", "CMD_CAS_4", "RECE_PRINT"

    Output:
        {"X": list[list[list[float]]], "mask": list[list[float]]}
        X shape: [1, MAX_LEN, n_features], mask shape: [1, MAX_LEN]
    """
    # 1. Records -> DataFrame (lowercase -> UPPERCASE for notebook compatibility)
    target_cols = ["CMD_CAS_1", "CMD_CAS_2", "CMD_CAS_3", "CMD_CAS_4", "RECE_PRINT"]

    df = pl.DataFrame(records).rename({
        "pid": "PID",
        "query_date": "QUERY_DATE",
        "institution": "INSTITUTION",
        "version": "VERSION",
        "nbre_cas_1": "NBRE_CAS_1",
        "nbre_cas_2": "NBRE_CAS_2",
        "nbre3": "NBRE3",
        "nbre_cas_4": "NBRE_CAS_4",
        "cmd_cas_1": "CMD_CAS_1",
        "cmd_cas_2": "CMD_CAS_2",
        "cmd_cas_3": "CMD_CAS_3",
        "cmd_cas_4": "CMD_CAS_4",
        "rece_print": "RECE_PRINT",
    })

    cols_to_drop = [c for c in target_cols if c != component]

    df = df.with_columns(pl.col("QUERY_DATE").cast(pl.Datetime)).rename({component: "target_col"})
    df = df.drop(cols_to_drop)
    df = df.with_columns(pl.col("VERSION").cast(pl.Utf8))

    # 2. EDA oracle preprocessing
    df = clean_noise(df)
    episodes_df = create_timesteps(df, time_col="QUERY_DATE")
    timesteps_df = aggregate_episodes(df)

    # 3. Data preparation on timesteps_df
    timesteps_df = remove_null_dates(timesteps_df)
    timesteps_df = compute_bill_diff(timesteps_df)
    timesteps_df = onehot_encode(timesteps_df, ["INSTITUTION", "VERSION"])

    # 4. Prepare sequences (filter by MAX_DUR/MAX_LEN, add timestep/idx)
    sequences_df = prepare_sequences(timesteps_df, episodes_df, MAX_DUR_MINUTES, MAX_LEN)

    # 5. Load artifacts
    scaler = load_scaler(component)

    # 6. Build arrays (using pre-fitted scaler)
    X, mask = build_arrays_for_inference(
        timesteps_df, episodes_df, MAX_LEN, MAX_DUR_MINUTES, scaler, component
    )

    # 7. Extract single PID
    pid_indices = sequences_df.filter(pl.col("PID") == pid)["idx"].to_numpy()
    if len(pid_indices) == 0:
        n_features = X.shape[2]
        return {
            "X": np.zeros((1, MAX_LEN, n_features), dtype=np.float32).tolist(),
            "mask": np.zeros((1, MAX_LEN), dtype=np.float32).tolist(),
            "episode_start_timestamp": None
        }

    idx = pid_indices[0]
    
    # Get episode start timestamp from episodes_df for this PID
    episode_timestamp = episodes_df.filter(pl.col("PID") == pid)["timestamp"].head(1)
    episode_start_timestamp = episode_timestamp[0] if len(episode_timestamp) > 0 else None
    
    return {
        "X": X[idx:idx+1].tolist(),
        "mask": mask[idx:idx+1].tolist(),
        "episode_start_timestamp": episode_start_timestamp
    }


def clean_noise(df: pl.DataFrame):
    df = df.with_columns(
        Event=pl.when(pl.col("target_col") == 4)
            .then(1)
            .otherwise(0)
    )

    df_cleaned = df.filter(
        ~((pl.col("Event") == 1) & (pl.col("Event").shift(1).fill_null(0).over("PID") == 1))
    )

    return df_cleaned


def aggregate_episodes(df: pl.DataFrame):
    df_sorted = df.with_columns(
        pl.col("QUERY_DATE").cast(pl.Datetime).alias("start_time")
    ).sort(["PID", "QUERY_DATE"])

    value_cols = [c for c in df.columns if c not in ("PID", "QUERY_DATE", "DATE_CREATE")] + ["seq_id"]

    aggregated_df = (
        df_sorted.with_columns(
            is_warning=(pl.col("target_col")==2).cast(pl.Int16),
            seq_id=pl.col("Event").shift(1).fill_null(0).cum_sum().over("PID"),
        )
        .sort(["PID", "start_time"])
        .with_columns(
            end_time=pl.col("start_time").shift(-1).over("PID"),
            timestep=pl.int_range(0, pl.len()).over("PID"),
            warnings_count=pl.col("is_warning").cum_sum().over(["PID", "seq_id"])
        )
    )

    return aggregated_df.select(["PID", "start_time", "end_time"] + value_cols + ["warnings_count"])


def create_timesteps(df: pl.DataFrame, time_col="QUERY_DATE"):
    # 1. Sort data
    df = df.sort(["PID", time_col])

    # 2. Create sequence IDs and aggregate into timesteps (episodes)
    timesteps_df = (
        df.with_columns(
            seq_id=pl.col("Event").shift(1).fill_null(0).cum_sum().over("PID")
        )
        .group_by(["PID", "seq_id"], maintain_order=True)
        .agg(
            (pl.max(time_col) - pl.min(time_col)).dt.total_minutes().alias("duration"),
            timestamp=pl.col(time_col).first(),
            instit=pl.min("INSTITUTION"),
            version=pl.min("VERSION"),
            warning_count=(pl.col("target_col")==2).sum(),
            sequence_length=pl.len(),
            event_occurred=pl.col("Event").max(),
        )
        .with_columns(
            prev_failure=pl.col("event_occurred").shift(1).fill_null(0).cum_sum().over("PID"),
            timestep=pl.int_range(0, pl.len()).over("PID")
        )
    )

    return timesteps_df


def compute_bill_diff(df: pl.DataFrame) -> pl.DataFrame:
    """Compute cassette bill differences (removed bills between consecutive rows)."""
    cassette_cols = ['NBRE_CAS_1', 'NBRE_CAS_2', 'NBRE3', 'NBRE_CAS_4']

    df_sorted = df.sort(["PID", "start_time"])

    removal_exprs = [
        (pl.col(col).shift(1).over("PID") - pl.col(col))
        .clip(lower_bound=0)
        .fill_null(0)
        .alias(f"{col}_removed")
        for col in cassette_cols
    ]

    df_with_removals = (
        df_sorted
        .with_columns(removal_exprs)
    )

    return df_with_removals.drop(cassette_cols)


def onehot_encode(df: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
    """One-hot encode categorical columns using predefined categories from training."""
    encoded_df = df.clone()
    for column in columns:
        # Get predefined categories for this column from training
        json_key = next((k for k, v in CATEGORY_COLUMN_MAP.items() if v == column), None)
        if json_key is None:
            # Fallback: derive from data (should not happen in production)
            categories = encoded_df.select(pl.col(column).unique()).get_column(column).to_list()
        else:
            categories = CATEGORIES.get(json_key, [])

        # Ensure column is string type for consistent comparison
        encoded_df = encoded_df.with_columns(pl.col(column).cast(pl.Utf8))

        # Create one-hot columns for ALL predefined categories
        one_hot_exprs = [
            (pl.col(column) == cat).cast(pl.Int8).alias(f"{column}_{cat}")
            for cat in categories
        ]
        encoded_df = encoded_df.with_columns(one_hot_exprs)

    encoded_df = encoded_df.drop(columns)
    return encoded_df


def join_tables(
    left_df: pl.DataFrame,
    right_df: pl.DataFrame,
    cols: list[str],
    left_ids: list[str],
    right_ids: list[str]
) -> pl.DataFrame:
    """Generic left join utility."""
    joint_df = left_df.join(
        right_df.select(cols),
        right_on=right_ids,
        left_on=left_ids,
        how='left'
    )
    return joint_df


def remove_null_dates(df: pl.DataFrame) -> pl.DataFrame:
    """Fill null end_time with start_time + 15 minutes."""
    return df.with_columns(
        end_time=pl.col("end_time").fill_null(
            pl.col("start_time") + pl.duration(minutes=15)
        )
    )


def get_feature_cols(timesteps_df: pl.DataFrame) -> list[str]:
    """Extract feature columns, excluding metadata columns."""
    return [c for c in timesteps_df.columns if c not in ("PID", "seq_id", "start_time", "end_time", "Event", "target_col")]


def prepare_sequences(
    timesteps_df: pl.DataFrame,
    episodes_df: pl.DataFrame,
    max_dur_minutes: float,
    max_len: int
) -> pl.DataFrame:
    """
    Prepare sequences by filtering by MAX_DUR and MAX_LEN (most recent),
    joining episode info, and adding sequential timestep/idx identifiers.
    """
    # 1. Map global episode index (idx)
    episode_ids = (
        episodes_df.select(["PID", "seq_id"]).unique(maintain_order=True)
        .with_row_index("idx")
    )

# 2. Calculate absolute end times for MAX_DUR filtering
    ep_end = (
        episodes_df
        .with_columns(ts_dt=pl.col("timestamp"))
        .with_columns(
            end_dt=pl.col("ts_dt") + pl.duration(minutes=pl.col("duration"))
        )
        .select(["PID", "seq_id", "end_dt"])
    )

    # 3. Join, Truncate, and Index
    sequences_df = (
        timesteps_df
        .with_columns(start_dt=pl.col("start_time"))
        .join(ep_end, on=["PID", "seq_id"], how="left")

        # STAGE 1: Duration threshold (Keep events within MAX_DUR from the end)
        .filter((pl.col("end_dt") - pl.col("start_dt")).dt.total_minutes() <= max_dur_minutes)
        .sort(["PID", "seq_id", "start_dt"])

        # STAGE 2: Length threshold (Keep the most recent MAX_LEN events)
        .group_by(["PID", "seq_id"], maintain_order=True)
        .tail(max_len)

        # STAGE 3: Add idx and timestep to the KEPT events
        .join(episode_ids, on=["PID", "seq_id"], how="left")
        .with_columns(
            timestep=pl.col("start_dt").rank("ordinal").over(["PID", "seq_id"]) - 1
        )

        # Clean up and final sort
        .drop(["start_dt", "end_dt"])
        .sort(["PID", "seq_id", "timestep"])
    )

    return sequences_df


def load_scaler(component: str) -> StandardScaler:
    """Load fitted scaler for a component from SCALERS_DIR."""
    scaler_path = SCALERS_DIR / f"scaler_{component}.pkl"
    if not scaler_path.exists():
        raise FileNotFoundError(f"Scaler not found for component {component} at {scaler_path}")
    with open(scaler_path, "rb") as f:
        return pickle.load(f)


def build_arrays_for_inference(
    timesteps_df: pl.DataFrame,
    episodes_df: pl.DataFrame,
    max_len: int,
    max_dur_minutes: float,
    scaler: StandardScaler,
    component: str
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build X, mask arrays for inference using pre-fitted scaler.
    Returns only (X, mask) - no duration/event for inference.
    """
    # 1. Prepare sequences using the unified function
    sequences_df = prepare_sequences(timesteps_df, episodes_df, max_dur_minutes, max_len)
    feature_cols = get_feature_cols(timesteps_df)

    episode_ids = (
        sequences_df.select(["PID", "seq_id"])
        .unique(maintain_order=True)
        .with_row_index("idx")
    )

    n_episodes = episode_ids.height
    n_features = len(feature_cols)

    # 2. Scale features on valid rows before padding
    raw_features = sequences_df.select(feature_cols).to_numpy()
    scaled_features = scaler.transform(raw_features)

    sequences_scaled_df = sequences_df.with_columns(
        pl.DataFrame(scaled_features, schema=feature_cols)
    )

    X_scaled = np.zeros((n_episodes, max_len, n_features), dtype=np.float32)
    mask = np.zeros((n_episodes, max_len), dtype=np.float32)

    # 3. Vectorize array building
    grouped_seqs = (
        sequences_scaled_df.select(["PID", "seq_id"] + feature_cols)
        .group_by(["PID", "seq_id"], maintain_order=True)
        .agg([pl.col(c) for c in feature_cols])
        .join(episode_ids, on=["PID", "seq_id"], how="inner")
        .sort("idx")
    )

    for row in grouped_seqs.iter_rows(named=True):
        idx = row["idx"]
        feats_array = np.array([row[c] for c in feature_cols], dtype=np.float32).T
        L = feats_array.shape[0]
        X_scaled[idx, :L, :] = feats_array
        mask[idx, :L] = 1.0

    return X_scaled, mask