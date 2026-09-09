from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from urllib.parse import urlparse

from app.config import get_settings


@dataclass(frozen=True)
class Institution:
    code: str
    name: str
    is_global: bool = False


@dataclass(frozen=True)
class User:
    id: int
    email: str
    password_hash: str
    institution_code: str | None
    created_at: datetime


def create_database_if_not_exists() -> None:
    """Create the PostgreSQL database if it doesn't exist."""
    settings = get_settings()
    
    # Parse the DSN to extract components
    parsed = urlparse(settings.postgres_dsn)
    db_name = parsed.path.lstrip('/')
    
    # Connect to the default 'postgres' database to check/create
    admin_dsn = settings.postgres_dsn.replace(f'/{db_name}', '/postgres')
    
    try:
        with psycopg.connect(admin_dsn) as conn:
            conn.autocommit = True
            with conn.cursor() as cursor:
                # Check if database exists
                cursor.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (db_name,)
                )
                exists = cursor.fetchone()
                
                if not exists:
                    cursor.execute(f'CREATE DATABASE "{db_name}"')
                    print(f"Created database '{db_name}'")
                else:
                    print(f"Database '{db_name}' already exists")
    except Exception as e:
        print(f"Warning: Could not create database: {e}")
        # If we can't connect to postgres, try connecting directly
        # This might happen if the database already exists but postgres db is not accessible
        try:
            with psycopg.connect(settings.postgres_dsn) as conn:
                print(f"Successfully connected to existing database '{db_name}'")
        except Exception as e2:
            print(f"Error: Could not connect to database: {e2}")
            raise


def get_connection() -> psycopg.Connection:
    return psycopg.connect(get_settings().postgres_dsn, row_factory=dict_row)


def init_auth_db() -> None:
    """Initialize the auth database schema."""
    # First ensure the database exists
    create_database_if_not_exists()
    
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS institutions (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                is_global BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_users (
                id BIGSERIAL PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                institution_code TEXT REFERENCES institutions(code),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        # Ensure INTELLIGENTSIA institution exists (code '0', global access)
        conn.execute(
            """
            INSERT INTO institutions (code, name, is_global, created_at, updated_at)
            VALUES ('0', 'INTELLIGENTSIA', TRUE, NOW(), NOW())
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name,
                is_global = EXCLUDED.is_global,
                updated_at = NOW()
            """
        )


def user_count() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM app_users").fetchone()
        return int(row["count"])


def get_user_by_email(email: str) -> User | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, email, password_hash, institution_code, created_at
            FROM app_users
            WHERE lower(email) = lower(%s)
            """,
            (email,),
        ).fetchone()
    return User(**row) if row else None


def get_user_by_id(user_id: int) -> User | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, email, password_hash, institution_code, created_at
            FROM app_users
            WHERE id = %s
            """,
            (user_id,),
        ).fetchone()
    return User(**row) if row else None


def create_user(
    email: str, password_hash: str, institution_code: str | None = None
) -> User:
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO app_users (email, password_hash, institution_code)
            VALUES (%s, %s, %s)
            RETURNING id, email, password_hash, institution_code, created_at
            """,
            (email.strip().lower(), password_hash, institution_code),
        ).fetchone()
    return User(**row)


def get_institutions() -> list:
    """Get all institutions for filter dropdown."""
    # This is a simple implementation - in production you might want to cache this
    # For now, we'll query the database
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT code, name, is_global FROM institutions ORDER BY code, name"
            ).fetchall()
        # Convert rows to actual dicts then to Institution objects
        return [Institution(code=dict(row)["code"], name=dict(row)["name"], is_global=dict(row)["is_global"]) for row in rows]
    except Exception:
        # Return default INTELLIGENTSIA institution if database unavailable
        return [Institution(code="0", name="INTELLIGENTSIA", is_global=True)]


def get_institution_by_code(code: str) -> Institution | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT code, name, is_global FROM institutions WHERE code = %s",
            (code,),
        ).fetchone()
    return Institution(**row) if row else None


async def sync_institutions_from_oracle() -> int:
    """Sync institutions from Oracle ST_BS_PARAMETRE table.
    Returns number of institutions synced.
    """
    # This function would connect to Oracle and sync institutions
    # For now, we just ensure INTELLIGENTSIA exists
    try:
        with get_connection() as conn:
            result = conn.execute(
                """
                INSERT INTO institutions (code, name, is_global, created_at, updated_at)
                VALUES ('0', 'INTELLIGENTSIA', TRUE, NOW(), NOW())
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name,
                    is_global = EXCLUDED.is_global,
                    updated_at = NOW()
                """
            )
        return 1
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Institution sync failed: %s", e)
        return 0