# app/models/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 1. Fetch the URL from the environment (e.g. Docker sets postgresql://admin:admin123@db:5432/sentinelx)
#    Defaults to local SQLite so the system runs smoothly out of the box without requiring external DB containers.
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "sqlite:///./sentinelx.db"
)

connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency to get the DB session in our API routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
