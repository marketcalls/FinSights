import os
from dotenv import load_dotenv
from perplexity import Perplexity

load_dotenv(override=True)  # loads variables from .env

api_key = os.getenv("PERPLEXITY_API_KEY")

client = Perplexity(api_key=api_key)

completion = client.chat.completions.create(
    messages=[
        {"role": "user", "content": "post market summary of indian stock market as on 28th Nov 2025"}
    ],
    model="sonar",
    web_search_options={
        "search_recency_filter": "hour",  # last 7 days
        "search_domain_filter": [
            # Indian financial portals
            "moneycontrol.com",
            "economictimes.indiatimes.com",
            "business-standard.com",
            "livemint.com",
            "financialexpress.com",
            "cnbctv18.com",

            # Global major financial news
            "reuters.com",
            "bloomberg.com",
            "ft.com"
        ],
        "max_search_results": 15
    }
)


# ✅ Print the full text response
print(f"Response: {completion.choices[0].message.content}")