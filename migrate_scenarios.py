"""
Database migration script to create scenarios table.
Run this script to add the scenarios table to your database.
"""
from app.database import engine, Base
from app.models import Scenario  # Import to register the model

def migrate():
    """Create all tables (will only create missing ones)."""
    print("Running database migration...")
    print("Creating scenarios table...")
    
    # This will create only the tables that don't exist yet
    Base.metadata.create_all(bind=engine)
    
    print("✓ Migration complete! Scenarios table created.")
    print("\nYou can now use the AI Scenarios feature.")

if __name__ == "__main__":
    migrate()
