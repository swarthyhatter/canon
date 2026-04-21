import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

_DEFAULT_DB_PATH = Path(__file__).parent / "canon.db"


def _db_path() -> Path:
    import os
    custom = os.getenv("CANON_STORE_DIR")
    if custom:
        return Path(custom) / "canon.db"
    return _DEFAULT_DB_PATH


@contextmanager
def _connect():
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init():
    """Create tables if they don't exist. Safe to call on every startup."""
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS batches (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                batch_run_id TEXT UNIQUE,
                type         TEXT,
                query        TEXT,
                context_text TEXT,
                raw_response TEXT
            );

            CREATE TABLE IF NOT EXISTS topics (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                batch_id          INTEGER REFERENCES batches(id),
                topic             TEXT,
                format_suggestion TEXT,
                template_id       TEXT
            );

            CREATE TABLE IF NOT EXISTS designs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                batch_id     INTEGER REFERENCES batches(id),
                topic_id     INTEGER REFERENCES topics(id),
                params_json  TEXT,
                template_id  TEXT,
                selected     INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                design_id            INTEGER REFERENCES designs(id),
                harmonica_session_id TEXT,
                join_url             TEXT,
                status               TEXT
            );
        """)


def new_batch_id() -> str:
    return uuid.uuid4().hex[:8]


# --- batches ---

def insert_batch(
    batch_run_id: str,
    type: str,
    query: str | None,
    context_text: str,
    raw_response: str,
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO batches
               (batch_run_id, type, query, context_text, raw_response)
               VALUES (?, ?, ?, ?, ?)""",
            (batch_run_id, type, query, context_text, raw_response),
        )
        return cur.lastrowid


def get_batch(batch_id: int) -> dict:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM batches WHERE id = ?", (batch_id,)
        ).fetchone()
    if row is None:
        raise KeyError(f"No batch with id={batch_id}")
    return dict(row)


def list_batches(type: str | None = None) -> list[dict]:
    with _connect() as conn:
        if type:
            rows = conn.execute(
                "SELECT * FROM batches WHERE type = ? ORDER BY created_at DESC",
                (type,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM batches ORDER BY created_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


# --- topics ---

def insert_topic(
    batch_id: int,
    topic: str,
    format_suggestion: str | None,
    template_id: str | None,
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO topics (batch_id, topic, format_suggestion, template_id)
               VALUES (?, ?, ?, ?)""",
            (batch_id, topic, format_suggestion, template_id),
        )
        return cur.lastrowid


def get_topic(topic_id: int) -> dict:
    with _connect() as conn:
        row = conn.execute(
            """SELECT t.*, b.query, b.batch_run_id, b.context_text
               FROM topics t JOIN batches b ON t.batch_id = b.id
               WHERE t.id = ?""",
            (topic_id,),
        ).fetchone()
    if row is None:
        raise KeyError(f"No topic with id={topic_id}")
    return dict(row)


def list_topics() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT t.*, b.query, b.batch_run_id
               FROM topics t JOIN batches b ON t.batch_id = b.id
               ORDER BY t.created_at DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def list_topics_for_batch(batch_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM topics WHERE batch_id = ? ORDER BY id",
            (batch_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# --- designs ---

def insert_design(
    batch_id: int,
    topic_id: int,
    params_json: str,
    template_id: str | None,
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO designs (batch_id, topic_id, params_json, template_id)
               VALUES (?, ?, ?, ?)""",
            (batch_id, topic_id, params_json, template_id),
        )
        return cur.lastrowid


def mark_selected(design_id: int):
    with _connect() as conn:
        conn.execute(
            "UPDATE designs SET selected = 1 WHERE id = ?", (design_id,)
        )


def get_design(design_id: int) -> dict:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM designs WHERE id = ?", (design_id,)
        ).fetchone()
    if row is None:
        raise KeyError(f"No design with id={design_id}")
    return dict(row)


def list_designs(topic_id: int | None = None) -> list[dict]:
    with _connect() as conn:
        if topic_id is not None:
            rows = conn.execute(
                "SELECT * FROM designs WHERE topic_id = ? ORDER BY created_at DESC",
                (topic_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM designs ORDER BY created_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def list_designs_for_batch(batch_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM designs WHERE batch_id = ? ORDER BY id",
            (batch_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# --- sessions ---

def insert_session(
    design_id: int | None,
    harmonica_session_id: str,
    join_url: str,
    status: str = "active",
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO sessions
               (design_id, harmonica_session_id, join_url, status)
               VALUES (?, ?, ?, ?)""",
            (design_id, harmonica_session_id, join_url, status),
        )
        return cur.lastrowid


def list_sessions() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]
