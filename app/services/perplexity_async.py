"""
Perplexity API client service for background job processing.
Uses the sync Perplexity client which is called from APScheduler's background threads.
This approach is non-blocking since APScheduler runs jobs in separate threads.
"""
import json
import re
import time
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from perplexity import Perplexity

from app.config import NEWS_SOURCES, TIMEZONE
from app.models.settings import Setting, ApiLog, NewsSource
from app.services.perplexity import MARKET_SUMMARY_SCHEMA, SECTOR_NEWS_SCHEMA


class AsyncPerplexityService:
    """
    Service for background Perplexity API calls.

    Note: Despite the name, this uses the sync Perplexity client because:
    1. Perplexity's async_ API only supports sonar-deep-research model
    2. APScheduler's BackgroundScheduler runs jobs in separate threads
    3. This makes API calls non-blocking to the main FastAPI application
    """

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
        return NEWS_SOURCES

    def _log_api_call(
        self,
        event_type: str,
        job_name: Optional[str],
        query: str,
        status: str,
        response_time_ms: int = 0,
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
        triggered_by: str = "scheduler",
        recency_filter: str = "day",
        use_structured: bool = True,
    ) -> dict:
        """
        Fetch market summary using sync API.
        Called from APScheduler background thread.
        """
        client = self._get_client()
        if not client:
            return {"error": "API key not configured", "content": None, "citations": []}

        news_sources = self._get_news_sources()
        start_time = time.time()

        try:
            # Build API call parameters
            api_params = {
                "messages": [{"role": "user", "content": query}],
                "model": "sonar-pro",
                "web_search_options": {
                    "search_recency_filter": recency_filter,
                    "search_domain_filter": news_sources,
                },
            }

            if use_structured:
                api_params["response_format"] = MARKET_SUMMARY_SCHEMA

            completion = client.chat.completions.create(**api_params)

            response_time = int((time.time() - start_time) * 1000)
            raw_content = completion.choices[0].message.content if completion.choices else ""

            # Parse content based on whether structured output was used
            if use_structured:
                try:
                    data = json.loads(raw_content)
                    content = self._format_structured_summary(data)
                    title = data.get("title", "")
                    sentiment_score = data.get("sentiment_score", 0)
                    sentiment_explanation = data.get("sentiment_explanation", "")
                except json.JSONDecodeError:
                    content = raw_content
                    title = ""
                    sentiment_score = 0
                    sentiment_explanation = ""
            else:
                content = raw_content
                title = ""
                sentiment_score = 0
                sentiment_explanation = ""

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
                "title": title,
                "citations": citations,
                "sentiment_score": sentiment_score,
                "sentiment_explanation": sentiment_explanation,
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

    def fetch_news(
        self,
        query: str,
        job_name: Optional[str] = None,
        triggered_by: str = "scheduler",
        recency_filter: str = "day",
        max_articles: int = 5,
    ) -> dict:
        """
        Fetch news articles using sync API.
        Called from APScheduler background thread.
        """
        client = self._get_client()
        if not client:
            return {"error": "API key not configured", "articles": [], "citations": []}

        news_sources = self._get_news_sources()
        start_time = time.time()

        try:
            prompt = f"""Find the latest {max_articles} news articles about: {query}

For each article, provide:
- A clear, concise title (max 150 characters)
- A brief 2-3 sentence summary
- The full article content with all important details, quotes, and analysis
- Any stock symbols mentioned (NSE/BSE format like RELIANCE, TCS, INFY)
- The market impact (positive, negative, or neutral)"""

            api_params = {
                "messages": [{"role": "user", "content": prompt}],
                "model": "sonar-pro",
                "web_search_options": {
                    "search_recency_filter": recency_filter,
                    "search_domain_filter": news_sources,
                },
                "response_format": SECTOR_NEWS_SCHEMA,
            }

            completion = client.chat.completions.create(**api_params)

            response_time = int((time.time() - start_time) * 1000)
            raw_content = completion.choices[0].message.content if completion.choices else ""

            # Parse JSON response
            try:
                data = json.loads(raw_content)
                articles = data.get("articles", [])
            except json.JSONDecodeError:
                articles = []

            # Extract citations
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
                news_count=len(articles),
                triggered_by=triggered_by,
            )

            return {
                "articles": articles,
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
            return {"error": str(e), "articles": [], "citations": []}

    def process_completed_summary(self, raw_content: str) -> dict:
        """
        Process a completed summary response.
        Parses the JSON and formats the content.
        """
        try:
            data = json.loads(raw_content)
            content = self._format_structured_summary(data)
            return {
                "title": data.get("title", ""),
                "content": content,
                "sentiment_score": data.get("sentiment_score", 0),
                "sentiment_explanation": data.get("sentiment_explanation", ""),
            }
        except json.JSONDecodeError:
            return {
                "title": "",
                "content": raw_content,
                "sentiment_score": 0,
                "sentiment_explanation": "",
            }

    def process_completed_news(self, raw_content: str) -> list[dict]:
        """
        Process a completed news response.
        Parses the JSON and returns list of articles.
        """
        try:
            data = json.loads(raw_content)
            return data.get("articles", [])
        except json.JSONDecodeError:
            return []

    def _format_structured_summary(self, data: dict) -> str:
        """Convert structured JSON summary to formatted markdown content."""
        parts = []

        if data.get("overview"):
            parts.append(f"## Overview\n\n{data['overview']}")

        if data.get("indices"):
            indices_text = "## Market Indices\n\n"
            for idx in data["indices"]:
                name = idx.get("name", "")
                value = idx.get("value", "")
                change = idx.get("change", "")
                if name:
                    indices_text += f"- **{name}**: {value} ({change})\n"
            parts.append(indices_text.strip())

        if data.get("key_points"):
            points_text = "## Key Points\n\n"
            for point in data["key_points"]:
                points_text += f"- {point}\n"
            parts.append(points_text.strip())

        if data.get("sectors"):
            sectors_text = "## Sector Performance\n\n"
            for sector in data["sectors"]:
                name = sector.get("name", "")
                perf = sector.get("performance", "")
                reason = sector.get("reason", "")
                if name:
                    sectors_text += f"- **{name}**: {perf}"
                    if reason:
                        sectors_text += f" - {reason}"
                    sectors_text += "\n"
            parts.append(sectors_text.strip())

        if data.get("market_sentiment"):
            sentiment = data["market_sentiment"].capitalize()
            parts.append(f"## Market Sentiment\n\n**{sentiment}**")

        return "\n\n".join(parts)

    def _clean_summary_text(self, text: str) -> str:
        """Clean up summary text by removing markdown formatting for preview display."""
        if not text:
            return ""

        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"__([^_]+)__", r"\1", text)
        text = re.sub(r"_([^_]+)_", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
        text = " ".join(text.split())

        if len(text) > 500:
            text = text[:500]
            last_space = text.rfind(" ")
            if last_space > 400:
                text = text[:last_space] + "..."

        return text
