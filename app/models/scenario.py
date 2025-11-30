"""
Scenario model for AI-generated what-if analysis.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import TIMEZONE


def get_ist_now():
    """Get current time in IST."""
    return datetime.now(TIMEZONE)


class Scenario(Base):
    """AI-generated scenario for news events."""
    
    __tablename__ = "scenarios"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Link to original news
    news_id = Column(Integer, ForeignKey("news.id", ondelete="CASCADE"), nullable=False)
    
    # Scenario details
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=False)
    probability = Column(Float, nullable=True)  # 0.0 to 1.0
    
    # Impact analysis (JSON structure)
    # Example: {"sectors": {"banking": "+2%", "it": "-1%"}, "indices": {"nifty": "+0.5%"}}
    impact_analysis = Column(JSON, nullable=True)
    
    # Historical precedents
    historical_context = Column(Text, nullable=True)
    
    # User parameters used to generate this scenario
    user_parameters = Column(JSON, nullable=True)
    # Example: {"rate_hike": "0.75%", "timeline": "immediate"}
    
    # Metadata
    created_at = Column(DateTime, default=get_ist_now)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationships
    news = relationship("News", back_populates="scenarios")
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "news_id": self.news_id,
            "title": self.title,
            "description": self.description,
            "probability": self.probability,
            "impact_analysis": self.impact_analysis,
            "historical_context": self.historical_context,
            "user_parameters": self.user_parameters,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
