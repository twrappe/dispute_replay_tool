"""
Creates the events table, required indexes, and grants app-user privileges.

Requires an admin (superuser) connection for DDL. Set ADMIN_DATABASE_URL in
.env to a superuser connection string. Falls back to DATABASE_URL if not set.

Run once before first use:
    python scripts/migrate.py
"""

import os
import sys

import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

load_dotenv()

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS events (
    event_id        UUID        PRIMARY KEY,
    transaction_id  TEXT        NOT NULL,
    event_type      TEXT        NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    pipeline_version TEXT       NOT NULL,
    model_version   TEXT,
    payload         JSONB       NOT NULL DEFAULT '{}'
);
"""

CREATE_INDEX_TXN_SQL = """
CREATE INDEX IF NOT EXISTS idx_events_transaction_id
    ON events (transaction_id);
"""

CREATE_INDEX_TYPE_SQL = """
CREATE INDEX IF NOT EXISTS idx_events_event_type
    ON events (event_type);
"""

# Revoke mutating privileges from PUBLIC so the table stays append-only.
REVOKE_SQL = """
REVOKE DELETE, UPDATE, TRUNCATE ON events FROM PUBLIC;
"""

# Grant the application role the minimum privileges it needs.
# APP_DB_USER defaults to replay_user; override via env if your role differs.
# Note: identifiers are injected via psycopg2.sql.Identifier — not string formatting.
GRANT_APP_USER_CHECK_SQL = """
SELECT 1 FROM pg_roles WHERE rolname = %s
"""


def migrate() -> None:
    admin_url = os.getenv("ADMIN_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not admin_url:
        print("ERROR: Neither ADMIN_DATABASE_URL nor DATABASE_URL is set.")
        print("Copy .env.example to .env and configure at least DATABASE_URL.")
        sys.exit(1)

    using_admin = bool(os.getenv("ADMIN_DATABASE_URL"))
    if not using_admin:
        print("WARNING: ADMIN_DATABASE_URL not set — falling back to DATABASE_URL.")
        print("         DDL and privilege grants may fail if the app user lacks superuser rights.")

    app_user = os.getenv("APP_DB_USER", "replay_user")

    conn = psycopg2.connect(admin_url)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            print("Creating events table...")
            cur.execute(CREATE_TABLE_SQL)
            print("Creating index on transaction_id...")
            cur.execute(CREATE_INDEX_TXN_SQL)
            print("Creating index on event_type...")
            cur.execute(CREATE_INDEX_TYPE_SQL)
            print("Revoking mutating privileges from PUBLIC...")
            cur.execute(REVOKE_SQL)
            print(f"Granting app-user privileges to '{app_user}'...")
            cur.execute(GRANT_APP_USER_CHECK_SQL, (app_user,))
            if cur.fetchone():
                role = sql.Identifier(app_user)
                cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
                cur.execute(sql.SQL("GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO {}").format(role))
                cur.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT ON TABLES TO {}").format(role))
            else:
                print(f"  WARNING: Role '{app_user}' does not exist — skipping grants.")
        print("Migration complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
