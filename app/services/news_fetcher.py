"""
News fetcher service - handles fetching and storing news.
"""
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
from sqlalchemy.orm import Session

from app.config import TIMEZONE
from app.models.news import News, Citation
from app.models.settings import ScheduleJob
from app.services.perplexity import PerplexityService
from app.services.cache import cache_manager


class NewsFetcher:
    """Service for fetching and storing news from Perplexity API."""

    def __init__(self, db: Session):
        self.db = db
        self.perplexity = PerplexityService(db)

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.replace("www.", "")
        except Exception:
            return ""

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime."""
        if not date_str:
            return None
        try:
            # Try common formats
            for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"]:
                try:
                    return datetime.strptime(date_str, fmt).replace(tzinfo=TIMEZONE)
                except ValueError:
                    continue
            return None
        except Exception:
            return None

    def fetch_market_summary(
        self,
        job_name: str,
        query: str,
        category: str = "market",
        subcategory: str = "general",
        triggered_by: str = "scheduler",
    ) -> Optional[News]:
        """
        Fetch a market summary using Chat Completions API.
        Creates a single news item with AI-generated summary.
        """
        result = self.perplexity.fetch_summary(
            query=query,
            job_name=job_name,
            triggered_by=triggered_by,
            recency_filter="hour",
        )

        if result.get("error") or not result.get("content"):
            return None

        # Create news item
        now = datetime.now(TIMEZONE)
        title = self._generate_title(subcategory, now)

        news = News(
            title=title,
            summary=result["content"][:500],
            content=result["content"],
            category=category,
            subcategory=subcategory,
            news_type="summary",
            fetched_at=now,
            is_published=True,
        )
        self.db.add(news)
        self.db.flush()  # Get ID

        # Add citations
        for citation in result.get("citations", []):
            cit = Citation(
                news_id=news.id,
                citation_index=citation.get("index"),
                url=citation.get("url"),
                title=citation.get("title"),
            )
            self.db.add(cit)

        self.db.commit()

        # Update cache
        cache_manager.add_news(news.to_dict())

        # Update job last_run
        job = self.db.query(ScheduleJob).filter(ScheduleJob.job_name == job_name).first()
        if job:
            job.last_run = now
            self.db.commit()

        return news

    def fetch_sector_news(
        self,
        job_name: str,
        query: str,
        category: str = "sector",
        subcategory: str = "general",
        triggered_by: str = "scheduler",
    ) -> list[News]:
        """
        Fetch sector news using Search API.
        Parses results into individual news items.
        """
        articles = self.perplexity.fetch_news_articles(
            queries=[query],
            job_name=job_name,
            triggered_by=triggered_by,
            max_results=5,
        )

        news_items = []
        now = datetime.now(TIMEZONE)

        for article in articles:
            snippet = article.get("snippet", "")
            source_url = article.get("url", "")
            source_name = article.get("title", "")
            source_domain = self._extract_domain(source_url)
            pub_date = self._parse_date(article.get("date"))

            # Parse snippet into individual articles
            parsed_articles = self.perplexity.parse_snippet_to_articles(
                snippet, source_url, source_name
            )

            for parsed in parsed_articles:
                # Check for duplicates
                existing = (
                    self.db.query(News)
                    .filter(News.title == parsed["title"])
                    .first()
                )
                if existing:
                    continue

                news = News(
                    title=parsed["title"],
                    summary=parsed["summary"],
                    source_url=parsed.get("source_url", source_url),
                    source_name=parsed.get("source_name", source_name),
                    source_domain=source_domain,
                    published_at=pub_date,
                    fetched_at=now,
                    category=category,
                    subcategory=subcategory,
                    news_type="article",
                    is_published=True,
                )
                self.db.add(news)
                news_items.append(news)

        self.db.commit()

        # Update cache
        for news in news_items:
            cache_manager.add_news(news.to_dict())

        # Update job last_run
        job = self.db.query(ScheduleJob).filter(ScheduleJob.job_name == job_name).first()
        if job:
            job.last_run = now
            self.db.commit()

        return news_items

    def fetch_stock_news(
        self,
        symbol: str,
        triggered_by: str = "manual",
    ) -> list[News]:
        """
        Fetch news for a specific stock symbol.
        """
        query = f"{symbol} stock news India NSE BSE latest"

        articles = self.perplexity.fetch_news_articles(
            queries=[query],
            job_name=f"stock_{symbol}",
            triggered_by=triggered_by,
            max_results=5,
        )

        news_items = []
        now = datetime.now(TIMEZONE)

        for article in articles:
            snippet = article.get("snippet", "")
            source_url = article.get("url", "")
            source_name = article.get("title", "")
            source_domain = self._extract_domain(source_url)

            # Parse snippet
            parsed_articles = self.perplexity.parse_snippet_to_articles(
                snippet, source_url, source_name
            )

            for parsed in parsed_articles:
                # Check for duplicates
                existing = (
                    self.db.query(News)
                    .filter(News.title == parsed["title"])
                    .first()
                )
                if existing:
                    continue

                news = News(
                    title=parsed["title"],
                    summary=parsed["summary"],
                    source_url=parsed.get("source_url", source_url),
                    source_name=parsed.get("source_name", source_name),
                    source_domain=source_domain,
                    fetched_at=now,
                    category="stock",
                    subcategory=symbol.lower(),
                    symbols=symbol.upper(),
                    news_type="article",
                    is_published=True,
                )
                self.db.add(news)
                news_items.append(news)

        self.db.commit()

        # Update cache
        news_dicts = [news.to_dict() for news in news_items]
        cache_manager.set_stock_news(symbol, news_dicts)

        return news_items

    def fetch_by_job(self, job: ScheduleJob, triggered_by: str = "scheduler") -> int:
        """
        Fetch news based on job configuration.
        Returns number of news items created.
        """
        category = job.category
        subcategory = job.subcategory

        # Market summaries use Chat Completions API
        if category == "market":
            news = self.fetch_market_summary(
                job_name=job.job_name,
                query=job.query_template,
                category=category,
                subcategory=subcategory,
                triggered_by=triggered_by,
            )
            return 1 if news else 0

        # Other categories use Search API
        news_items = self.fetch_sector_news(
            job_name=job.job_name,
            query=job.query_template,
            category=category,
            subcategory=subcategory,
            triggered_by=triggered_by,
        )
        return len(news_items)

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

    def fetch_all_jobs(self, triggered_by: str = "startup") -> dict:
        """
        Fetch news for all enabled jobs.
        Used on startup or manual refresh all.
        """
        jobs = self.db.query(ScheduleJob).filter(ScheduleJob.is_enabled == True).all()
        results = {"success": 0, "failed": 0, "total_news": 0}

        for job in jobs:
            try:
                count = self.fetch_by_job(job, triggered_by)
                results["success"] += 1
                results["total_news"] += count
            except Exception as e:
                results["failed"] += 1
                print(f"Error fetching {job.job_name}: {e}")

        return results
