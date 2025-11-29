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
from app.services.cache import cache_manager
from app.services.scheduler import scheduler_service
from app.services.perplexity import PerplexityService
from app.routers import public, admin


def init_default_admin(db: Session):
    """Create default admin user if none exists."""
    existing = db.query(User).first()
    if not existing:
        admin_user = User(username=ADMIN_DEFAULT_USERNAME)
        admin_user.set_password(ADMIN_DEFAULT_PASSWORD)
        db.add(admin_user)
        db.commit()
        print(f"Created default admin user: {ADMIN_DEFAULT_USERNAME}")


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

        # Load cache from database
        cache_manager.load_from_db(db)
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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "scheduler_running": scheduler_service.is_running(),
        "cache_stats": cache_manager.get_cache_stats(),
    }
