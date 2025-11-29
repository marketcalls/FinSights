import os
from dotenv import load_dotenv
from perplexity import Perplexity

load_dotenv(override=True)  # loads variables from .env

api_key = os.getenv("PERPLEXITY_API_KEY")

client = Perplexity(api_key=api_key)

# Multi-query search for sector-level Indian market news
# Comprehensive research with related queries
search = client.search.create(
    query=[
       "latest AUTO sector news India market",
        "latest PHARMA sector news India market",
        "latest BANKING sector news India market",
        "latest IT sector news India market"
    ],
    max_results=5
)

# Access results for each query
for i, query_results in enumerate(search.results):
    print(f"Results for query {i+1}:")
    for result in query_results:
        print(f"  result: {result}")
    print("---")