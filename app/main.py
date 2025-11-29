"""
FastAPI application entry point.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.database import init_db, SessionLocal
from app.config import DEBUG, ADMIN_DEFAULT_USERNAME, ADMIN_DEFAULT_PASSWORD
from app.models.user import User
from app.models.settings import StockSymbol
from app.services.cache import cache_manager
from app.services.scheduler import scheduler_service
from app.services.perplexity import PerplexityService
from app.routers import public, admin
from app.template_filters import register_filters

# Nifty 50 stock symbols data
NIFTY_50_SYMBOLS = [
    ("ADANIENT", "Adani Enterprises Ltd", "Conglomerate"),
    ("ADANIPORTS", "Adani Ports & SEZ Ltd", "Infrastructure"),
    ("APOLLOHOSP", "Apollo Hospitals Enterprise Ltd", "Healthcare"),
    ("ASIANPAINT", "Asian Paints Ltd", "Consumer Goods"),
    ("AXISBANK", "Axis Bank Ltd", "Banking"),
    ("BAJAJ-AUTO", "Bajaj Auto Ltd", "Automobile"),
    ("BAJFINANCE", "Bajaj Finance Ltd", "Financial Services"),
    ("BAJAJFINSV", "Bajaj Finserv Ltd", "Financial Services"),
    ("BPCL", "Bharat Petroleum Corp Ltd", "Oil & Gas"),
    ("BHARTIARTL", "Bharti Airtel Ltd", "Telecom"),
    ("BRITANNIA", "Britannia Industries Ltd", "FMCG"),
    ("CIPLA", "Cipla Ltd", "Pharma"),
    ("COALINDIA", "Coal India Ltd", "Mining"),
    ("DIVISLAB", "Divi's Laboratories Ltd", "Pharma"),
    ("DRREDDY", "Dr. Reddy's Laboratories Ltd", "Pharma"),
    ("EICHERMOT", "Eicher Motors Ltd", "Automobile"),
    ("GRASIM", "Grasim Industries Ltd", "Cement"),
    ("HCLTECH", "HCL Technologies Ltd", "IT"),
    ("HDFCBANK", "HDFC Bank Ltd", "Banking"),
    ("HDFCLIFE", "HDFC Life Insurance Co Ltd", "Insurance"),
    ("HEROMOTOCO", "Hero MotoCorp Ltd", "Automobile"),
    ("HINDALCO", "Hindalco Industries Ltd", "Metals"),
    ("HINDUNILVR", "Hindustan Unilever Ltd", "FMCG"),
    ("ICICIBANK", "ICICI Bank Ltd", "Banking"),
    ("ITC", "ITC Ltd", "FMCG"),
    ("INDUSINDBK", "IndusInd Bank Ltd", "Banking"),
    ("INFY", "Infosys Ltd", "IT"),
    ("JSWSTEEL", "JSW Steel Ltd", "Metals"),
    ("KOTAKBANK", "Kotak Mahindra Bank Ltd", "Banking"),
    ("LT", "Larsen & Toubro Ltd", "Infrastructure"),
    ("M&M", "Mahindra & Mahindra Ltd", "Automobile"),
    ("MARUTI", "Maruti Suzuki India Ltd", "Automobile"),
    ("NTPC", "NTPC Ltd", "Power"),
    ("NESTLEIND", "Nestle India Ltd", "FMCG"),
    ("ONGC", "Oil & Natural Gas Corp Ltd", "Oil & Gas"),
    ("POWERGRID", "Power Grid Corp of India Ltd", "Power"),
    ("RELIANCE", "Reliance Industries Ltd", "Conglomerate"),
    ("SBILIFE", "SBI Life Insurance Co Ltd", "Insurance"),
    ("SBIN", "State Bank of India", "Banking"),
    ("SUNPHARMA", "Sun Pharmaceutical Industries Ltd", "Pharma"),
    ("TCS", "Tata Consultancy Services Ltd", "IT"),
    ("TATACONSUM", "Tata Consumer Products Ltd", "FMCG"),
    ("TATAMOTORS", "Tata Motors Ltd", "Automobile"),
    ("TATASTEEL", "Tata Steel Ltd", "Metals"),
    ("TECHM", "Tech Mahindra Ltd", "IT"),
    ("TITAN", "Titan Company Ltd", "Consumer Goods"),
    ("ULTRACEMCO", "UltraTech Cement Ltd", "Cement"),
    ("UPL", "UPL Ltd", "Chemicals"),
    ("WIPRO", "Wipro Ltd", "IT"),
]


def init_default_admin(db: Session):
    """Create default admin user if none exists."""
    existing = db.query(User).first()
    if not existing:
        admin_user = User(username=ADMIN_DEFAULT_USERNAME)
        admin_user.set_password(ADMIN_DEFAULT_PASSWORD)
        db.add(admin_user)
        db.commit()
        print(f"Created default admin user: {ADMIN_DEFAULT_USERNAME}")


def seed_nifty50_symbols(db: Session):
    """Seed Nifty 50 stock symbols if not already present."""
    existing_count = db.query(StockSymbol).count()
    if existing_count > 0:
        print(f"Stock symbols already seeded: {existing_count} symbols")
        return

    for symbol, company_name, sector in NIFTY_50_SYMBOLS:
        stock = StockSymbol(
            symbol=symbol,
            company_name=company_name,
            sector=sector,
            is_nifty50=True,
            is_active=True,
        )
        db.add(stock)

    db.commit()
    print(f"Seeded {len(NIFTY_50_SYMBOLS)} Nifty 50 symbols")


def startup_fetch(db: Session):
    """Fetch news on startup if cache is empty and API is configured."""
    perplexity = PerplexityService(db)
    if not perplexity.is_configured():
        print("Perplexity API key not configured. Skipping startup fetch.")
        return

    stats = cache_manager.get_cache_stats()
    if stats["total_news"] == 0:
        print("Cache is empty. Fetching initial news...")
        from app.services.news_fetcher import NewsFetcher
        fetcher = NewsFetcher(db)
        results = fetcher.fetch_all_jobs(triggered_by="startup")
        print(f"Startup fetch complete: {results}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    print("Starting FinSights...")

    # Initialize database
    init_db()
    print("Database initialized")

    # Create default admin
    db = SessionLocal()
    try:
        init_default_admin(db)

        # Seed Nifty 50 symbols
        seed_nifty50_symbols(db)

        # Load cache from database
        cache_manager.load_from_db(db)
        cache_manager.load_symbols(db)
        print(f"Cache loaded: {cache_manager.get_cache_stats()}")

        # Initialize scheduler
        scheduler_service.init_jobs_from_db(db)
        scheduler_service.start()
        print("Scheduler started")

        # Startup fetch if needed (async/background)
        # startup_fetch(db)  # Uncomment to enable auto-fetch on startup

    finally:
        db.close()

    yield

    # Shutdown
    print("Shutting down FinSights...")
    scheduler_service.stop()
    print("Scheduler stopped")


# Create FastAPI app
app = FastAPI(
    title="FinSights",
    description="Indian Market News Summary Platform",
    version="1.0.0",
    lifespan=lifespan,
    debug=DEBUG,
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(public.router)
app.include_router(admin.router)

# Register custom template filters
register_filters(public.templates)
register_filters(admin.templates)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "scheduler_running": scheduler_service.is_running(),
        "cache_stats": cache_manager.get_cache_stats(),
    }
