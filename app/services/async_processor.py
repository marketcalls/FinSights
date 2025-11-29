"""
Background job processor service.
Processes scheduled jobs by calling Perplexity API and saving results.
Runs in APScheduler's background threads, so it's non-blocking to the main app.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.config import TIMEZONE
from app.database import SessionLocal
from app.models.news import News, Citation
from app.models.settings import ScheduleJob
from app.services.perplexity_async import AsyncPerplexityService
from app.services.cache import cache_manager


class AsyncRequestProcessor:
    """
    Processes scheduled jobs by fetching from Perplexity API.

    This runs in APScheduler's background thread, making it non-blocking
    to the main FastAPI application.
    """

    def __init__(self, db: Session):
        self.db = db
        self.perplexity = AsyncPerplexityService(db)

    def process_job(
        self,
        job: ScheduleJob,
        triggered_by: str = "scheduler",
    ) -> dict:
        """
        Process a job by fetching data and creating news items.
        Returns result with success status and news count.
        """
        if job.category == "market":
            return self._process_market_job(job, triggered_by)
        else:
            return self._process_news_job(job, triggered_by)

    def _process_market_job(
        self,
        job: ScheduleJob,
        triggered_by: str,
    ) -> dict:
        """Process a market summary job."""
        result = self.perplexity.fetch_summary(
            query=job.query_template,
            job_name=job.job_name,
            triggered_by=triggered_by,
            recency_filter="hour",
            use_structured=True,
        )

        if result.get("error"):
            return {"success": False, "error": result["error"], "news_count": 0}

        # Create news item from result
        now = datetime.now(TIMEZONE)
        title = result.get("title") or self._generate_title(job.subcategory, now)
        content = result.get("content", "")
        summary_text = self.perplexity._clean_summary_text(content)
        if len(summary_text) > 500:
            summary_text = summary_text[:497] + "..."

        news = News(
            title=title,
            summary=summary_text,
            content=content,
            category=job.category or "market",
            subcategory=job.subcategory or "general",
            news_type="summary",
            sentiment_score=result.get("sentiment_score", 0),
            sentiment_explanation=result.get("sentiment_explanation", ""),
            fetched_at=now,
            is_published=True,
        )
        self.db.add(news)
        self.db.flush()

        # Add citations
        for cit in result.get("citations", []):
            citation = Citation(
                news_id=news.id,
                citation_index=cit.get("index"),
                url=cit.get("url"),
                title=cit.get("title"),
            )
            self.db.add(citation)

        # Update job last_run
        job.last_run = now
        self.db.commit()

        cache_manager.add_news(news.to_dict())

        return {"success": True, "news_count": 1}

    def _process_news_job(
        self,
        job: ScheduleJob,
        triggered_by: str,
    ) -> dict:
        """Process a news articles job."""
        result = self.perplexity.fetch_news(
            query=job.query_template,
            job_name=job.job_name,
            triggered_by=triggered_by,
            recency_filter="day",
            max_articles=5,
        )

        if result.get("error"):
            return {"success": False, "error": result["error"], "news_count": 0}

        articles = result.get("articles", [])
        citations = result.get("citations", [])
        now = datetime.now(TIMEZONE)
        news_count = 0

        for article in articles:
            title = article.get("title", "")
            summary = article.get("summary", "")
            content = article.get("content", "")
            stocks = article.get("stocks_mentioned", [])
            sentiment_score = article.get("sentiment_score", 0)
            sentiment_explanation = article.get("sentiment_explanation", "")

            if not title or len(title) < 10:
                continue

            # Check for duplicates
            existing = self.db.query(News).filter(News.title == title).first()
            if existing:
                continue

            symbols = ",".join(stocks) if stocks else None

            news = News(
                title=title[:500],
                summary=summary or content[:500],
                content=content,
                fetched_at=now,
                category=job.category or "sector",
                subcategory=job.subcategory or "general",
                symbols=symbols,
                sentiment_score=sentiment_score,
                sentiment_explanation=sentiment_explanation,
                news_type="article",
                is_published=True,
            )
            self.db.add(news)
            self.db.flush()

            # Add citations
            for cit in citations:
                citation = Citation(
                    news_id=news.id,
                    citation_index=cit.get("index"),
                    url=cit.get("url"),
                    title=cit.get("title"),
                )
                self.db.add(citation)

            cache_manager.add_news(news.to_dict())
            news_count += 1

        # Update job last_run
        job.last_run = now
        self.db.commit()

        return {"success": True, "news_count": news_count}

    def _generate_title(self, subcategory: str, dt: datetime) -> str:
        """Generate a title for market summary."""
        date_str = dt.strftime("%d %b %Y")
        titles = {
            "pre_market": f"Pre-Market Analysis - {date_str}",
            "morning": f"Morning Market Update - {date_str}",
            "midday": f"Mid-Day Market Summary - {date_str}",
            "post_market": f"Post-Market Summary - {date_str}",
            "evening": f"Evening Market Wrap - {date_str}",
        }
        return titles.get(subcategory, f"Market Update - {date_str}")


def create_processor() -> AsyncRequestProcessor:
    """Factory function to create a processor with a new database session."""
    db = SessionLocal()
    return AsyncRequestProcessor(db)
