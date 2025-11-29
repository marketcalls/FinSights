"""
Perplexity API client service.
Uses the official perplexity SDK.
"""
import json
import time
import re
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from perplexity import Perplexity

from app.config import NEWS_SOURCES, TIMEZONE
from app.models.settings import Setting, ApiLog, NewsSource


# JSON Schema for structured market summary response
MARKET_SUMMARY_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "A concise headline for the market summary (max 100 chars)"
                },
                "overview": {
                    "type": "string",
                    "description": "A 2-3 sentence overview of market conditions"
                },
                "key_points": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-5 key bullet points about the market"
                },
                "sectors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "performance": {"type": "string"},
                            "reason": {"type": "string"}
                        },
                        "required": ["name", "performance"]
                    },
                    "description": "Top performing or notable sectors"
                },
                "market_sentiment": {
                    "type": "string",
                    "enum": ["bullish", "bearish", "neutral", "mixed"],
                    "description": "Overall market sentiment"
                },
                "indices": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "value": {"type": "string"},
                            "change": {"type": "string"}
                        },
                        "required": ["name"]
                    },
                    "description": "Major index movements (Nifty, Sensex, etc.)"
                },
                "sentiment_score": {
                    "type": "integer",
                    "minimum": -10,
                    "maximum": 10,
                    "description": "Sentiment score from -10 (extremely negative) to +10 (extremely positive), 0 is neutral"
                },
                "sentiment_explanation": {
                    "type": "string",
                    "description": "Brief explanation of why this sentiment score was given, highlighting key positive or negative factors"
                }
            },
            "required": ["title", "overview", "key_points", "market_sentiment", "sentiment_score", "sentiment_explanation"]
        }
    }
}

# JSON Schema for structured sector news response
SECTOR_NEWS_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "schema": {
            "type": "object",
            "properties": {
                "articles": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Article headline (max 150 chars)"
                            },
                            "summary": {
                                "type": "string",
                                "description": "Brief summary of the article (2-3 sentences)"
                            },
                            "content": {
                                "type": "string",
                                "description": "Full article content with all key details and analysis"
                            },
                            "stocks_mentioned": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Stock symbols mentioned (e.g., RELIANCE, TCS)"
                            },
                            "impact": {
                                "type": "string",
                                "enum": ["positive", "negative", "neutral"],
                                "description": "Market impact of the news"
                            },
                            "sentiment_score": {
                                "type": "integer",
                                "minimum": -10,
                                "maximum": 10,
                                "description": "Sentiment score from -10 (extremely negative) to +10 (extremely positive). Examples: Company profit up 50% = +8, Minor delay in project = -2, Routine announcement = 0, Major fraud discovered = -9, Record-breaking growth = +9"
                            },
                            "sentiment_explanation": {
                                "type": "string",
                                "description": "1-2 sentence explanation of the sentiment score. Explain what makes this news positive or negative for investors/market"
                            }
                        },
                        "required": ["title", "summary", "content", "sentiment_score", "sentiment_explanation"]
                    }
                }
            },
            "required": ["articles"]
        }
    }
}


class PerplexityService:
    """Service for interacting with Perplexity API using official SDK."""

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
        use_structured: bool = True,
    ) -> dict:
        """
        Fetch an AI-generated summary using Chat Completions API.
        Used for market summaries. Uses structured JSON response for better formatting.
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

            # Add structured output schema if requested
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
                # Try to extract title from first line if it's a header
                if raw_content:
                    lines = raw_content.strip().split('\n')
                    first_line = lines[0].strip()
                    if first_line.startswith('#'):
                        title = first_line.lstrip('#').strip()
                    elif len(first_line) < 150 and not first_line.startswith('-'):
                        title = first_line

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

    def _format_structured_summary(self, data: dict) -> str:
        """Convert structured JSON summary to formatted markdown content."""
        parts = []

        # Overview
        if data.get("overview"):
            parts.append(f"## Overview\n\n{data['overview']}")

        # Market Indices
        if data.get("indices"):
            indices_text = "## Market Indices\n\n"
            for idx in data["indices"]:
                name = idx.get("name", "")
                value = idx.get("value", "")
                change = idx.get("change", "")
                if name:
                    indices_text += f"- **{name}**: {value} ({change})\n"
            parts.append(indices_text.strip())

        # Key Points
        if data.get("key_points"):
            points_text = "## Key Points\n\n"
            for point in data["key_points"]:
                points_text += f"- {point}\n"
            parts.append(points_text.strip())

        # Sector Performance
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

        # Market Sentiment
        if data.get("market_sentiment"):
            sentiment = data["market_sentiment"].capitalize()
            parts.append(f"## Market Sentiment\n\n**{sentiment}**")

        return "\n\n".join(parts)

    def fetch_structured_news(
        self,
        query: str,
        job_name: Optional[str] = None,
        triggered_by: str = "manual",
        recency_filter: str = "day",
        max_articles: int = 5,
    ) -> list[dict]:
        """
        Fetch news articles using Perplexity API with structured output.
        Returns structured articles directly from JSON response.
        """
        client = self._get_client()
        if not client:
            return []

        news_sources = self._get_news_sources()
        start_time = time.time()
        try:
            # Build prompt for news extraction
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
                # Fallback to parsing markdown if JSON fails
                articles = self._parse_news_response(raw_content)

            # Extract citations
            citations = []
            if hasattr(completion, "citations") and completion.citations:
                for i, url in enumerate(completion.citations, 1):
                    citations.append({"index": i, "url": url, "title": None})

            # Add citations to articles
            for article in articles:
                article["citations"] = citations

            self._log_api_call(
                event_type="api_call",
                job_name=job_name,
                query=query,
                status="success",
                response_time_ms=response_time,
                news_count=len(articles),
                triggered_by=triggered_by,
            )

            return articles

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
            return []

    def _parse_news_response(self, content: str) -> list[dict]:
        """Parse markdown news response into structured articles."""
        if not content:
            return []

        articles = []
        # Split by article separators
        parts = re.split(r'\n---+\n|\n## ', content)

        for part in parts:
            part = part.strip()
            if not part or len(part) < 50:
                continue

            article = {
                "title": "",
                "summary": "",
                "content": "",
                "stocks_mentioned": [],
                "sentiment_score": 0,
                "sentiment_explanation": "",
            }

            lines = part.split('\n')

            # First line is usually the title
            first_line = lines[0].strip()
            if first_line.startswith('#'):
                article["title"] = first_line.lstrip('#').strip()
            elif first_line.startswith('['):
                # Handle [Title] format
                match = re.match(r'\[([^\]]+)\]', first_line)
                if match:
                    article["title"] = match.group(1)
            else:
                article["title"] = first_line[:150]

            # Parse the rest of the content
            current_section = "content"
            content_parts = []

            for line in lines[1:]:
                line_lower = line.lower().strip()

                if line_lower.startswith('**summary:**') or line_lower.startswith('summary:'):
                    article["summary"] = re.sub(r'\*\*summary:\*\*|\bsummary:', '', line, flags=re.IGNORECASE).strip()
                elif line_lower.startswith('**content:**') or line_lower.startswith('content:'):
                    current_section = "content"
                    content_parts.append(re.sub(r'\*\*content:\*\*|\bcontent:', '', line, flags=re.IGNORECASE).strip())
                elif line_lower.startswith('**stocks:**') or line_lower.startswith('stocks:'):
                    stocks_text = re.sub(r'\*\*stocks:\*\*|\bstocks:', '', line, flags=re.IGNORECASE).strip()
                    stocks = re.findall(r'[A-Z]{2,}', stocks_text)
                    article["stocks_mentioned"] = stocks
                elif line_lower.startswith('**sentiment:**') or line_lower.startswith('sentiment:'):
                    sentiment_text = re.sub(r'\*\*sentiment:\*\*|\bsentiment:', '', line, flags=re.IGNORECASE).strip()
                    # Try to extract score
                    score_match = re.search(r'([+-]?\d+)', sentiment_text)
                    if score_match:
                        article["sentiment_score"] = int(score_match.group(1))
                    article["sentiment_explanation"] = sentiment_text
                else:
                    if current_section == "content":
                        content_parts.append(line)

            article["content"] = '\n'.join(content_parts).strip()

            # Use content as summary if summary is empty
            if not article["summary"] and article["content"]:
                article["summary"] = article["content"][:300]

            if article["title"] and len(article["title"]) > 10:
                articles.append(article)

        return articles

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

            # Clean up summary - remove markdown but preserve structure
            summary = self._clean_summary_text(summary)

            if title and len(title) > 10:
                articles.append({
                    "title": title[:200],
                    "summary": summary or title,
                    "source_url": source_url,
                    "source_name": source_name,
                })

        return articles

    def _clean_summary_text(self, text: str) -> str:
        """
        Clean up summary text by removing markdown formatting for preview display.
        """
        if not text:
            return ""

        # Remove markdown bold/italic
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"__([^_]+)__", r"\1", text)
        text = re.sub(r"_([^_]+)_", r"\1", text)

        # Remove links but keep text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

        # Remove bullet points
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)

        # Remove numbered lists
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)

        # Clean up multiple spaces/newlines
        text = " ".join(text.split())

        # Truncate at word boundary
        if len(text) > 500:
            text = text[:500]
            last_space = text.rfind(" ")
            if last_space > 400:
                text = text[:last_space] + "..."

        return text

    def format_market_summary(self, content: str) -> str:
        """
        Format AI-generated market summary with proper structure.
        Ensures consistent formatting with headers and bullet points.
        """
        if not content:
            return ""

        # Check if content already has structure
        has_headers = bool(re.search(r"^#{1,3}\s", content, re.MULTILINE))
        has_bullets = bool(re.search(r"^\s*[-*]\s", content, re.MULTILINE))

        if has_headers or has_bullets:
            # Content is already formatted, just clean it up
            return content.strip()

        # Split into paragraphs and format
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

        if len(paragraphs) == 1:
            # Single paragraph - try to split into points
            sentences = re.split(r"(?<=[.!?])\s+", paragraphs[0])
            if len(sentences) > 3:
                # Convert to bullet points
                formatted = "## Summary\n\n"
                for sentence in sentences:
                    if len(sentence) > 20:
                        formatted += f"- {sentence}\n"
                return formatted.strip()
            else:
                return content.strip()

        # Multiple paragraphs - add structure
        formatted_parts = []
        for i, para in enumerate(paragraphs):
            if i == 0:
                formatted_parts.append(f"## Overview\n\n{para}")
            else:
                formatted_parts.append(para)

        return "\n\n".join(formatted_parts)
