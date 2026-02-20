"""Application settings model (key-value store)."""

from sqlalchemy import String, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class AppSettings(TimestampMixin, Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)

    @staticmethod
    def get_value(session, key: str, default: str | None = None) -> str | None:
        setting = session.query(AppSettings).filter_by(key=key).first()
        return setting.value if setting else default

    @staticmethod
    def set_value(session, key: str, value: str) -> None:
        setting = session.query(AppSettings).filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = AppSettings(key=key, value=value)
            session.add(setting)
