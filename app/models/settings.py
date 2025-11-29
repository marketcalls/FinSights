"""
Settings and scheduler models.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import TIMEZONE


def get_ist_now():
    """Get current time in IST."""
    return datetime.now(TIMEZONE)


class Setting(Base):
    """Application settings stored in database."""

    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)
    encrypted = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=get_ist_now, onupdate=get_ist_now)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationship
    updater = relationship("User")


class ScheduleJob(Base):
    """Scheduler job configuration."""

    __tablename__ = "schedule_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_name = Column(String(100), unique=True, nullable=False)
    category = Column(String(50), nullable=False)
    subcategory = Column(String(50), nullable=True)
    query_template = Column(Text, nullable=False)
    schedule_type = Column(String(20), nullable=False)  # 'cron' or 'interval'
    cron_time = Column(String(10), nullable=True)  # '07:00' for cron jobs (IST)
    interval_minutes = Column(Integer, nullable=True)  # For interval jobs
    is_enabled = Column(Boolean, default=True)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=get_ist_now)

    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "job_name": self.job_name,
            "category": self.category,
            "subcategory": self.subcategory,
            "query_template": self.query_template,
            "schedule_type": self.schedule_type,
            "cron_time": self.cron_time,
            "interval_minutes": self.interval_minutes,
            "is_enabled": self.is_enabled,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
        }


class NewsSource(Base):
    """Trusted news sources for Perplexity API filtering."""

    __tablename__ = "news_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain = Column(String(200), unique=True, nullable=False)
    name = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # Higher priority = more important
    created_at = Column(DateTime, default=get_ist_now)

    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "domain": self.domain,
            "name": self.name,
            "is_active": self.is_active,
            "priority": self.priority,
        }


class ApiLog(Base):
    """API call and event logs."""

    __tablename__ = "api_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=get_ist_now)
    event_type = Column(String(50), nullable=False)  # 'api_call', 'scheduler', 'manual_trigger', 'error'
    job_name = Column(String(100), nullable=True)
    query = Column(Text, nullable=True)
    status = Column(String(20), nullable=True)  # 'success', 'failed', 'pending'
    response_time_ms = Column(Integer, nullable=True)
    news_count = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    triggered_by = Column(String(100), nullable=True)  # 'scheduler', 'admin:username', 'startup'

    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "event_type": self.event_type,
            "job_name": self.job_name,
            "query": self.query,
            "status": self.status,
            "response_time_ms": self.response_time_ms,
            "news_count": self.news_count,
            "error_message": self.error_message,
            "triggered_by": self.triggered_by,
        }
