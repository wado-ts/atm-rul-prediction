from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
import hashlib
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
    created_at: datetime
    first_name: str | None = None
    last_name: str | None = None
    institution_code: str | None = None


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
    


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
                first_name TEXT,
                last_name TEXT,
                institution_code TEXT REFERENCES institutions(code),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token_hash TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
                expires_at TIMESTAMPTZ NOT NULL,
                used_at TIMESTAMPTZ
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS password_reset_tokens_user_idx ON password_reset_tokens(user_id)"
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
            SELECT id, email, password_hash, first_name, last_name, institution_code, created_at
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
            SELECT id, email, password_hash, first_name, last_name, institution_code, created_at
            FROM app_users
            WHERE id = %s
            """,
            (user_id,),
        ).fetchone()
    return User(**row) if row else None


def create_password_reset_token(user_id: int, token: str, expires_at: datetime) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM password_reset_tokens WHERE user_id = %s OR expires_at <= NOW()",
            (user_id,),
        )
        conn.execute(
            """
            INSERT INTO password_reset_tokens (token_hash, user_id, expires_at)
            VALUES (%s, %s, %s)
            """,
            (_hash_reset_token(token), user_id, expires_at),
        )


def reset_password_with_token(token: str, password_hash: str) -> bool:
    token_hash = _hash_reset_token(token)
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        row = conn.execute(
            """
            UPDATE app_users
            SET password_hash = %s
            WHERE id = (
                SELECT user_id
                FROM password_reset_tokens
                WHERE token_hash = %s
                  AND used_at IS NULL
                  AND expires_at > %s
                FOR UPDATE
            )
            RETURNING id
            """,
            (password_hash, token_hash, now),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE password_reset_tokens SET used_at = %s WHERE token_hash = %s",
            (now, token_hash),
        )
    return True


def create_user(
    email: str, 
    password_hash: str, 
    first_name: str | None = None,
    last_name: str | None = None,
    institution_code: str | None = None
) -> User:
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO app_users (email, password_hash, first_name, last_name, institution_code)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, email, password_hash, first_name, last_name, institution_code, created_at
            """,
            (email.strip().lower(), password_hash, first_name, last_name, institution_code),
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
    try:
        from app.database import get_pool
        import oracledb
        
        # Fetch institutions from Oracle
        institutions_from_oracle = []
        try:
            pool = get_pool()
            with pool.acquire() as connection:
                with connection.cursor() as cursor:
                    # Query ST_BS_PARAMETRE for institution data
                    cursor.execute(
                        """
                        SELECT DISTINCT 
                            CODE as code,
                            INTITULE as name
                        FROM ST_BS_PARAMETRE
                        WHERE code IS NOT NULL
                        AND INTITULE IS NOT NULL
                        """
                    )
                    for row in cursor:
                        institutions_from_oracle.append({
                            'code': str(row[0]) if row[0] else None,
                            'name': str(row[1]) if row[1] else None
                        })
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Could not fetch institutions from Oracle: %s", e)
        
        # Sync to PostgreSQL
        synced_count = 0
        with get_connection() as conn:
            # Ensure INTELLIGENTSIA exists first
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
            synced_count += 1
            
            # Sync institutions from Oracle
            for inst in institutions_from_oracle:
                if inst['code'] and inst['name']:
                    conn.execute(
                        """
                        INSERT INTO institutions (code, name, is_global, created_at, updated_at)
                        VALUES (%s, %s, FALSE, NOW(), NOW())
                        ON CONFLICT (code) DO UPDATE SET
                            name = EXCLUDED.name,
                            updated_at = NOW()
                        """,
                        (inst['code'], inst['name'])
                    )
                    synced_count += 1
        
        return synced_count
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Institution sync failed: %s", e)
        return 0