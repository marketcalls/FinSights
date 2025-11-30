"""
Scenario generation service using Perplexity AI.
"""
import json
import time
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from app.config import TIMEZONE
from app.models.news import News
from app.models.scenario import Scenario
from app.services.perplexity import PerplexityService


# JSON Schema for structured scenario response
SCENARIO_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "schema": {
            "type": "object",
            "properties": {
                "scenarios": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Short title for this scenario (max 100 chars)"
                            },
                            "description": {
                                "type": "string",
                                "description": "Detailed explanation of this scenario"
                            },
                            "probability": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                                "description": "Probability estimate (0.0 to 1.0)"
                            },
                            "impact_analysis": {
                                "type": "object",
                                "properties": {
                                    "sectors": {
                                        "type": "object",
                                        "description": "Sector-wise impact (e.g., {'banking': '+2%'})"
                                    },
                                    "indices": {
                                        "type": "object",
                                        "description": "Index impact (e.g., {'nifty': '+0.5%'})"
                                    },
                                    "stocks": {
                                        "type": "object",
                                        "description": "Stock-specific impact"
                                    }
                                }
                            },
                            "historical_context": {
                                "type": "string",
                                "description": "Similar past events and outcomes"
                            }
                        },
                        "required": ["title", "description", "probability"]
                    }
                }
            },
            "required": ["scenarios"]
        }
    }
}


class ScenarioService:
    """Service for generating AI-powered what-if scenarios."""
    
    def __init__(self, db: Session):
        self.db = db
        self.perplexity_service = PerplexityService(db)
    
    def generate_scenarios(
        self,
        news_id: int,
        user_parameters: Optional[Dict] = None,
        num_scenarios: int = 3,
        user_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Generate alternative scenarios for a news event.
        
        Args:
            news_id: ID of the news article
            user_parameters: User-provided parameters for scenario customization
            num_scenarios: Number of scenarios to generate (default 3)
            user_id: User requesting scenarios
            
        Returns:
            List of scenario dictionaries
        """
        # Get news from database
        news = self.db.query(News).filter(News.id == news_id).first()
        if not news:
            return []
        
        # Check if scenarios already exist (cache for 24 hours)
        existing_scenarios = self.db.query(Scenario).filter(
            Scenario.news_id == news_id
        ).all()
        
        if existing_scenarios and len(existing_scenarios) >= num_scenarios:
            return [s.to_dict() for s in existing_scenarios]
        
        # Build prompt for AI
        prompt = self._build_scenario_prompt(news, user_parameters, num_scenarios)
        
        # Call Perplexity AI
        client = self.perplexity_service._get_client()
        if not client:
            return []
        
        try:
            start_time = time.time()
            
            completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="sonar-pro",
                response_format=SCENARIO_SCHEMA,
                web_search_options={
                    "search_recency_filter": "month",
                }
            )
            
            response_time = int((time.time() - start_time) * 1000)
            raw_content = completion.choices[0].message.content if completion.choices else ""
            
            # Parse JSON response
            data = json.loads(raw_content)
            scenarios_data = data.get("scenarios", [])
            
            # Save scenarios to database
            saved_scenarios = []
            for scenario_data in scenarios_data:
                scenario = Scenario(
                    news_id=news_id,
                    title=scenario_data.get("title", ""),
                    description=scenario_data.get("description", ""),
                    probability=scenario_data.get("probability"),
                    impact_analysis=scenario_data.get("impact_analysis"),
                    historical_context=scenario_data.get("historical_context"),
                    user_parameters=user_parameters,
                    created_by=user_id,
                )
                self.db.add(scenario)
                saved_scenarios.append(scenario)
            
            self.db.commit()
            
            # Log API call
            self.perplexity_service._log_api_call(
                event_type="scenario_generation",
                job_name=f"scenarios_{news_id}",
                query=prompt[:200],
                status="success",
                response_time_ms=response_time,
                news_count=len(scenarios_data),
                triggered_by=f"user:{user_id}" if user_id else "system"
            )
            
            return [s.to_dict() for s in saved_scenarios]
            
        except Exception as e:
            print(f"Error generating scenarios: {e}")
            # Log error
            self.perplexity_service._log_api_call(
                event_type="scenario_generation",
                job_name=f"scenarios_{news_id}",
                query=prompt[:200] if 'prompt' in locals() else "",
                status="failed",
                response_time_ms=0,
                error_message=str(e),
                triggered_by=f"user:{user_id}" if user_id else "system"
            )
            return []
    
    def _build_scenario_prompt(
        self,
        news: News,
        user_parameters: Optional[Dict],
        num_scenarios: int
    ) -> str:
        """Build the AI prompt for scenario generation."""
        
        base_prompt = f"""Analyze this Indian stock market news and generate {num_scenarios} alternative "what-if" scenarios:

**Original News:**
Title: {news.title}
Summary: {news.summary}
Category: {news.category} - {news.subcategory or 'general'}
{f'Stocks Mentioned: {news.symbols}' if news.symbols else ''}

**Task:**
Generate {num_scenarios} plausible alternative scenarios exploring different outcomes or variations of this event.

For each scenario provide:
1. A clear title describing the scenario (max 80 characters)
2. Detailed description of what could happen (2-3 sentences)
3. Estimated probability (0.0 to 1.0) based on historical data and current context
4. Impact analysis on:
   - Key sectors (Banking, IT, Pharma, Auto, Energy, etc.) - show percentage impact
   - Major indices (Nifty, Sensex, Bank Nifty) - show percentage impact
   - Specific stocks if mentioned in the news
5. Historical context: When has something similar happened before? (1-2 sentences)

**Guidelines:**
- Scenarios should be realistic and data-driven
- Include both optimistic and pessimistic scenarios
- Consider macroeconomic factors, global impact, policy implications
- Use percentage estimates for market impacts (e.g., "+2.5%", "-1.8%")
- Reference specific historical events when applicable
- Make probabilities add up to approximately 1.0
"""
        
        # Add user parameters if provided
        if user_parameters:
            base_prompt += f"\n**User Constraints:**\n"
            for key, value in user_parameters.items():
                base_prompt += f"- {key}: {value}\n"
        
        return base_prompt
    
    def get_scenarios_for_news(self, news_id: int) -> List[Dict]:
        """Get all existing scenarios for a news article."""
        scenarios = self.db.query(Scenario).filter(Scenario.news_id == news_id).all()
        return [s.to_dict() for s in scenarios]
