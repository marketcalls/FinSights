import os
from dotenv import load_dotenv
from perplexity import Perplexity

load_dotenv(override=True)  # loads variables from .env

api_key = os.getenv("PERPLEXITY_API_KEY")

client = Perplexity(api_key=api_key)

completion = client.chat.completions.create(
    messages=[
        {
            "role": "user",
            "content": "Find the top 3 trending AI startups with recent funding. Include company name, funding amount, and focus area."
        }
    ],
    model="sonar-pro",
    response_format={
        "type": "json_schema",
        "json_schema": {
            "schema": {
                "type": "object",
                "properties": {
                    "startups": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "company_name": {"type": "string"},
                                "funding_amount": {"type": "string"},
                                "focus_area": {"type": "string"}
                            },
                            "required": ["company_name", "funding_amount", "focus_area"]
                        }
                    }
                },
                "required": ["startups"]
            }
        }
    }
)

print(completion.choices[0].message.content)