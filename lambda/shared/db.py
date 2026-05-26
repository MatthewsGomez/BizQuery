"""
Database connection module for Lambda functions.

Provides a connection pool backed by psycopg2, reading all connection
parameters from environment variables so that no credentials are
hard-coded in source code.

Environment variables required:
    DB_HOST     – PostgreSQL host (e.g. RDS endpoint or RDS Proxy endpoint)
    DB_PORT     – PostgreSQL port (default: 5432)
    DB_NAME     – Database name
    DB_USER     – Database user
    DB_PASSWORD – Database password
"""

import os
import logging
from contextlib import contextmanager
from typing import Generator

import psycopg2
from psycopg2 import pool as psycopg2_pool

logger = logging.getLogger(__name__)

# Module-level connection pool — created once per Lambda container lifetime.
# Using a SimpleConnectionPool is appropriate for Lambda because each
# container handles one request at a time; a ThreadedConnectionPool would be
# needed only if the handler spawned threads.
_connection_pool: psycopg2_pool.SimpleConnectionPool | None = None

# Pool size bounds — kept small because Lambda containers are single-threaded.
_POOL_MIN_CONN = 1
_POOL_MAX_CONN = 5


def _get_db_config() -> dict:
    """Read database connection parameters from environment variables."""
    return {
        "host": os.environ["DB_HOST"],
        "port": int(os.environ.get("DB_PORT", "5432")),
        "dbname": os.environ["DB_NAME"],
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
        "connect_timeout": 10,
        "sslmode": os.environ.get("DB_SSLMODE", "require"),
    }


def get_connection_pool() -> psycopg2_pool.SimpleConnectionPool:
    """
    Return the module-level connection pool, creating it on first call.

    The pool is reused across invocations within the same Lambda container,
    which avoids the overhead of establishing a new TCP connection on every
    request.
    """
    global _connection_pool

    if _connection_pool is None or _connection_pool.closed:
        config = _get_db_config()
        logger.info(
            "Creating connection pool: host=%s port=%s dbname=%s user=%s",
            config["host"],
            config["port"],
            config["dbname"],
            config["user"],
        )
        _connection_pool = psycopg2_pool.SimpleConnectionPool(
            _POOL_MIN_CONN,
            _POOL_MAX_CONN,
            **config,
        )

    return _connection_pool


@contextmanager
def get_db_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """
    Context manager that yields a database connection from the pool and
    returns it when the block exits (even on exception).

    Usage::

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                row = cur.fetchone()
    """
    pool = get_connection_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
