"""
News model for storing news articles and summaries.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import TIMEZONE


def get_ist_now():
    """Get current time in IST."""
    return datetime.now(TIMEZONE)


class News(Base):
    """News article or summary model."""

    __tablename__ = "news"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Content
    title = Column(String(500), nullable=False)
    summary = Column(Text, nullable=False)
    content = Column(Text, nullable=True)

    # Source Information
    source_url = Column(String(1000), nullable=True)
    source_name = Column(String(200), nullable=True)
    source_domain = Column(String(200), nullable=True)

    # Dates (stored in IST)
    published_at = Column(DateTime, nullable=True)
    last_updated_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=get_ist_now)

    # Classification
    category = Column(String(50), nullable=False)  # market, sector, macro, regulation, stock
    subcategory = Column(String(50), nullable=True)  # pre_market, auto, rbi, etc.
    news_type = Column(String(20), default="article")  # 'summary' or 'article'

    # Stock Association
    symbols = Column(String(500), nullable=True)  # Comma-separated: "RELIANCE,TCS,INFY"

    # Admin Control
    is_published = Column(Boolean, default=True)
    is_manual = Column(Boolean, default=False)
    is_featured = Column(Boolean, default=False)

    # Audit
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, nullable=True, onupdate=get_ist_now)

    # Relationships
    citations = relationship("Citation", back_populates="news", cascade="all, delete-orphan")
    creator = relationship("User", back_populates="news_items")

    # Indexes
    __table_args__ = (
        Index("idx_news_category", "category", "subcategory", "is_published"),
        Index("idx_news_symbols", "symbols"),
        Index("idx_news_fetched", "fetched_at"),
    )

    def to_dict(self):
        """Convert to dictionary for cache storage."""
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "content": self.content,
            "source_url": self.source_url,
            "source_name": self.source_name,
            "source_domain": self.source_domain,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "category": self.category,
            "subcategory": self.subcategory,
            "news_type": self.news_type,
            "symbols": self.symbols,
            "is_published": self.is_published,
            "is_manual": self.is_manual,
            "is_featured": self.is_featured,
            "citations": [c.to_dict() for c in self.citations] if self.citations else [],
        }


class Citation(Base):
    """Citation/source reference for news summaries."""

    __tablename__ = "citations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    news_id = Column(Integer, ForeignKey("news.id", ondelete="CASCADE"), nullable=False)
    citation_index = Column(Integer, nullable=True)  # [1], [2], etc.
    url = Column(String(1000), nullable=False)
    title = Column(String(500), nullable=True)

    # Relationship
    news = relationship("News", back_populates="citations")

    def to_dict(self):
        """Convert to dictionary."""
        return {
            "index": self.citation_index,
            "url": self.url,
            "title": self.title,
        }
