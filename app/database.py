"""
Database configuration and session management.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import DATABASE_URL, DATA_DIR

# Ensure the data directory exists
DATA_DIR.mkdir(exist_ok=True)

# Create database engine
# For SQLite, we need to handle the connection string format
db_url = DATABASE_URL
if db_url.startswith("sqlite:///./"):
    db_url = f"sqlite:///{DATA_DIR}/finsights.db"

engine = create_engine(
    db_url,
    connect_args={"check_same_thread": False} if "sqlite" in db_url else {},
    echo=False,
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """
    Dependency that provides a database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize the database by creating all tables.
    """
    from app.models import news, user, settings  # noqa: F401
    Base.metadata.create_all(bind=engine)
