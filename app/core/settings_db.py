from app.core.database import SessionLocal

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def ensure_table():
    db = SessionLocal()
    try:
        db.execute(CREATE_SQL)
        db.commit()
    finally:
        db.close()


def get_setting(key: str, default: str | None = None) -> str | None:
    db = SessionLocal()
    try:
        r = db.execute("SELECT value FROM app_settings WHERE key = :k", {"k": key}).fetchone()
        if not r:
            return default
        return r[0]
    finally:
        db.close()


def set_setting(key: str, value: str) -> None:
    db = SessionLocal()
    try:
        # upsert
        db.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (:k, :v)", {"k": key, "v": value})
        db.commit()
    finally:
        db.close()
