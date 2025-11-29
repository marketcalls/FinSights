"""
Public routes for the news website.
"""
import csv
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import CATEGORY_NAMES, SUBCATEGORY_NAMES, SYMBOLS_FILE
from app.services.cache import cache_manager
from app.services.news_fetcher import NewsFetcher

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_symbols() -> list[str]:
    """Load stock symbols from CSV file."""
    symbols = []
    try:
        with open(SYMBOLS_FILE, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "SYMBOL" in row:
                    symbols.append(row["SYMBOL"])
    except Exception:
        symbols = ["RELIANCE", "TCS", "HDFC", "INFY", "ICICIBANK", "SBIN"]
    return symbols


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Homepage with all news categories."""
    return templates.TemplateResponse("public/home.html", {
        "request": request,
        "latest_news": cache_manager.get_latest_news(20),
        "market_news": cache_manager.get_news_by_category("market", limit=10),
        "sector_news": cache_manager.get_news_by_category("sector", limit=12),
        "macro_news": cache_manager.get_news_by_category("macro", limit=10),
        "regulation_news": cache_manager.get_news_by_category("regulation", limit=10),
        "category_names": CATEGORY_NAMES,
        "subcategory_names": SUBCATEGORY_NAMES,
    })


@router.get("/news/{news_id}", response_class=HTMLResponse)
async def news_detail(request: Request, news_id: int, db: Session = Depends(get_db)):
    """Individual news detail page."""
    from app.models.news import News

    # Try cache first
    news = cache_manager.get_news_by_id(news_id)

    # Fallback to database if not in cache
    if not news:
        news_obj = db.query(News).filter(News.id == news_id, News.is_published == True).first()
        if news_obj:
            news = news_obj.to_dict()
            # Add to cache for future requests
            cache_manager.add_news(news)

    if not news:
        return templates.TemplateResponse("public/search.html", {
            "request": request,
            "query": "",
            "results": [],
            "category_names": CATEGORY_NAMES,
            "error": "News not found",
        })

    return templates.TemplateResponse("public/news_detail.html", {
        "request": request,
        "news": news,
        "category_names": CATEGORY_NAMES,
        "subcategory_names": SUBCATEGORY_NAMES,
    })


@router.get("/category/{category}", response_class=HTMLResponse)
async def category_page(request: Request, category: str):
    """News by category."""
    news_items = cache_manager.get_news_by_category(category, limit=50)

    # Get unique subcategories
    subcategories = list(set(
        n.get("subcategory") for n in news_items if n.get("subcategory")
    ))

    return templates.TemplateResponse("public/category.html", {
        "request": request,
        "news_items": news_items,
        "category": category,
        "subcategory": None,
        "category_name": CATEGORY_NAMES.get(category, category.title()),
        "subcategory_name": None,
        "subcategories": subcategories,
        "category_names": CATEGORY_NAMES,
        "subcategory_names": SUBCATEGORY_NAMES,
    })


@router.get("/category/{category}/{subcategory}", response_class=HTMLResponse)
async def subcategory_page(request: Request, category: str, subcategory: str):
    """News by subcategory."""
    news_items = cache_manager.get_news_by_category(category, subcategory, limit=50)

    return templates.TemplateResponse("public/category.html", {
        "request": request,
        "news_items": news_items,
        "category": category,
        "subcategory": subcategory,
        "category_name": CATEGORY_NAMES.get(category, category.title()),
        "subcategory_name": SUBCATEGORY_NAMES.get(subcategory, subcategory.replace("_", " ").title()),
        "subcategories": [],
        "category_names": CATEGORY_NAMES,
        "subcategory_names": SUBCATEGORY_NAMES,
    })


@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = "",
    symbol: str = "",
    db: Session = Depends(get_db)
):
    """Search news by text or symbol."""
    results = []
    query = q or symbol

    if symbol:
        # Redirect to stock page
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/stock/{symbol.upper()}", status_code=302)

    if q:
        results = cache_manager.search_news(q, limit=50)

    return templates.TemplateResponse("public/search.html", {
        "request": request,
        "query": query,
        "results": results,
        "category_names": CATEGORY_NAMES,
    })


@router.get("/stock/{symbol}", response_class=HTMLResponse)
async def stock_page(request: Request, symbol: str, db: Session = Depends(get_db)):
    """Stock-specific news page."""
    symbol = symbol.upper()

    # Try to get from cache first
    news_items = cache_manager.get_stock_news(symbol, limit=20)

    # If no cached news, try to fetch
    if not news_items:
        fetcher = NewsFetcher(db)
        fetched = fetcher.fetch_stock_news(symbol, triggered_by="on_demand")
        news_items = [n.to_dict() for n in fetched]

    # Get popular symbols for navigation
    all_symbols = get_symbols()
    popular_symbols = all_symbols[:20] if len(all_symbols) > 20 else all_symbols

    return templates.TemplateResponse("public/stock.html", {
        "request": request,
        "symbol": symbol,
        "news_items": news_items,
        "popular_symbols": popular_symbols,
        "category_names": CATEGORY_NAMES,
    })
