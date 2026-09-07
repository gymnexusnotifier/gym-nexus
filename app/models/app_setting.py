from sqlalchemy import Column, String, Text

from app.core.database import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=True)