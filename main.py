"""
Entry point for the FastAPI application.

Run from project root:
  python main.py
  OR
  python -m uvicorn app.main:app --reload
"""
import uvicorn
from app.main import app
from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower()
    )
