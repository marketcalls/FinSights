"""
Perplexity API client service.
"""
import time
import re
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from perplexity import Perplexity

from app.config import NEWS_SOURCES, TIMEZONE
from app.models.settings import Setting, ApiLog, NewsSource


class PerplexityService:
    """Service for interacting with Perplexity API."""

    def __init__(self, db: Session):
        self.db = db
        self._client: Optional[Perplexity] = None

    def _get_api_key(self) -> Optional[str]:
        """Get API key from database settings."""
        setting = self.db.query(Setting).filter(Setting.key == "perplexity_api_key").first()
        if setting and setting.value:
            return setting.value
        return None

    def _get_client(self) -> Optional[Perplexity]:
        """Get or create Perplexity client."""
        if self._client is None:
            api_key = self._get_api_key()
            if api_key:
                self._client = Perplexity(api_key=api_key)
        return self._client

    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return self._get_api_key() is not None

    def _get_news_sources(self) -> list[str]:
        """Get active news sources from database, fallback to config."""
        sources = self.db.query(NewsSource).filter(NewsSource.is_active == True).all()
        if sources:
            return [s.domain for s in sources]
        # Fallback to hardcoded config if no sources in DB
        return NEWS_SOURCES

    def validate_api_key(self, api_key: str) -> tuple[bool, str]:
        """Validate an API key by making a test call. Returns (success, message)."""
        try:
            client = Perplexity(api_key=api_key)
            # Make a simple test query
            completion = client.chat.completions.create(
                messages=[{"role": "user", "content": "Say hello"}],
                model="sonar",
            )
            if completion and completion.choices:
                return True, "API key is valid!"
            return False, "API returned empty response"
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "unauthorized" in error_msg.lower():
                return False, "Invalid API key (unauthorized)"
            elif "429" in error_msg:
                return False, "Rate limit exceeded - but key appears valid"
            else:
                return False, f"Validation error: {error_msg[:100]}"

    def set_api_key(self, api_key: str, user_id: Optional[int] = None) -> bool:
        """Set or update the API key."""
        setting = self.db.query(Setting).filter(Setting.key == "perplexity_api_key").first()
        if setting:
            setting.value = api_key
            setting.updated_by = user_id
            setting.updated_at = datetime.now(TIMEZONE)
        else:
            setting = Setting(
                key="perplexity_api_key",
                value=api_key,
                encrypted=False,  # In production, encrypt this
                updated_by=user_id,
                updated_at=datetime.now(TIMEZONE),
            )
            self.db.add(setting)
        self.db.commit()
        self.db.refresh(setting)  # Refresh to ensure data is persisted
        self._client = None  # Reset client to use new key
        return True

    def _log_api_call(
        self,
        event_type: str,
        job_name: Optional[str],
        query: str,
        status: str,
        response_time_ms: int,
        news_count: int = 0,
        error_message: Optional[str] = None,
        triggered_by: str = "manual",
    ):
        """Log an API call to the database."""
        log = ApiLog(
            timestamp=datetime.now(TIMEZONE),
            event_type=event_type,
            job_name=job_name,
            query=query,
            status=status,
            response_time_ms=response_time_ms,
            news_count=news_count,
            error_message=error_message,
            triggered_by=triggered_by,
        )
        self.db.add(log)
        self.db.commit()

    def fetch_summary(
        self,
        query: str,
        job_name: Optional[str] = None,
        triggered_by: str = "manual",
        recency_filter: str = "day",
    ) -> dict:
        """
        Fetch an AI-generated summary using Chat Completions API.
        Used for market summaries.
        """
        client = self._get_client()
        if not client:
            return {"error": "API key not configured", "content": None, "citations": []}

        start_time = time.time()
        try:
            # Get active news sources from database
            news_sources = self._get_news_sources()

            completion = client.chat.completions.create(
                messages=[{"role": "user", "content": query}],
                model="sonar",
                web_search_options={
                    "search_recency_filter": recency_filter,
                    "search_domain_filter": news_sources,
                    "max_search_results": 15,
                },
            )

            response_time = int((time.time() - start_time) * 1000)
            content = completion.choices[0].message.content if completion.choices else ""

            # Extract citations if available
            citations = []
            if hasattr(completion, "citations") and completion.citations:
                for i, url in enumerate(completion.citations, 1):
                    citations.append({"index": i, "url": url, "title": None})

            self._log_api_call(
                event_type="api_call",
                job_name=job_name,
                query=query,
                status="success",
                response_time_ms=response_time,
                news_count=1,
                triggered_by=triggered_by,
            )

            return {
                "content": content,
                "citations": citations,
                "fetched_at": datetime.now(TIMEZONE).isoformat(),
            }

        except Exception as e:
            response_time = int((time.time() - start_time) * 1000)
            self._log_api_call(
                event_type="api_call",
                job_name=job_name,
                query=query,
                status="failed",
                response_time_ms=response_time,
                error_message=str(e),
                triggered_by=triggered_by,
            )
            return {"error": str(e), "content": None, "citations": []}

    def fetch_news_articles(
        self,
        queries: list[str],
        job_name: Optional[str] = None,
        triggered_by: str = "manual",
        max_results: int = 5,
    ) -> list[dict]:
        """
        Fetch news articles using Search API.
        Used for sector/stock-specific news.
        """
        client = self._get_client()
        if not client:
            return []

        start_time = time.time()
        all_articles = []

        try:
            search = client.search.create(
                query=queries,
                max_results=max_results,
            )

            response_time = int((time.time() - start_time) * 1000)

            # Process results
            if hasattr(search, "results") and search.results:
                for query_results in search.results:
                    article = {}
                    for result in query_results:
                        if isinstance(result, tuple) and len(result) == 2:
                            key, value = result
                            article[key] = value
                    if article:
                        all_articles.append(article)

            self._log_api_call(
                event_type="api_call",
                job_name=job_name,
                query=", ".join(queries),
                status="success",
                response_time_ms=response_time,
                news_count=len(all_articles),
                triggered_by=triggered_by,
            )

            return all_articles

        except Exception as e:
            response_time = int((time.time() - start_time) * 1000)
            self._log_api_call(
                event_type="api_call",
                job_name=job_name,
                query=", ".join(queries),
                status="failed",
                response_time_ms=response_time,
                error_message=str(e),
                triggered_by=triggered_by,
            )
            return []

    def parse_snippet_to_articles(self, snippet: str, source_url: str, source_name: str) -> list[dict]:
        """
        Parse a long snippet containing multiple headlines into individual articles.
        """
        articles = []

        # Split by markdown headers (## or ###)
        parts = re.split(r"(?=#{2,3}\s)", snippet)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Extract title (first line or header)
            lines = part.split("\n")
            title = lines[0].lstrip("#").strip()

            # Skip if title is too short or generic
            if len(title) < 10 or title.lower() in ["news", "more", "latest"]:
                continue

            # Get summary (remaining text)
            summary = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

            # Clean up summary
            summary = re.sub(r"\s+", " ", summary)
            summary = summary[:500] if len(summary) > 500 else summary

            if title and len(title) > 10:
                articles.append({
                    "title": title[:200],
                    "summary": summary or title,
                    "source_url": source_url,
                    "source_name": source_name,
                })

        return articles
