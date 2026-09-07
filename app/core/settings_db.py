from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.app_setting import AppSetting


def get_setting(key: str, default: str | None = None) -> str | None:
    db = SessionLocal()
    try:
        setting = db.execute(
            select(AppSetting).where(AppSetting.key == key)
        ).scalar_one_or_none()
        return setting.value if setting is not None else default
    finally:
        db.close()


def set_setting(key: str, value: str) -> None:
    db = SessionLocal()
    try:
        setting = db.get(AppSetting, key)
        if setting is None:
            setting = AppSetting(key=key, value=value)
            db.add(setting)
        else:
            setting.value = value
        db.commit()
    finally:
        db.close()
