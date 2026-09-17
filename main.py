"""
Root-level ASGI entrypoint for Render and deployment environments.
Allows starting the FastAPI application with:
    uvicorn main:app --host 0.0.0.0 --port $PORT
as well as:
    uvicorn backend.main:app --host 0.0.0.0 --port $PORT
"""

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from backend.main import app

__all__ = ["app"]
