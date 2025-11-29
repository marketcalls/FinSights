"""
User model for admin authentication.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import TIMEZONE
import bcrypt


def get_ist_now():
    """Get current time in IST."""
    return datetime.now(TIMEZONE)


class User(Base):
    """Admin user model."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=get_ist_now)

    # Relationships
    news_items = relationship("News", back_populates="creator")

    def set_password(self, password: str):
        """Hash and set the password."""
        self.password_hash = bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt()
        ).decode("utf-8")

    def check_password(self, password: str) -> bool:
        """Verify password against hash."""
        return bcrypt.checkpw(
            password.encode("utf-8"),
            self.password_hash.encode("utf-8")
        )

    def to_dict(self):
        """Convert to dictionary (excluding sensitive data)."""
        return {
            "id": self.id,
            "username": self.username,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
