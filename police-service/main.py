"""Entry point so the README command works from this folder:
    uvicorn main:app --port 8001 --reload
(The factory form also works: uvicorn app.main:create_app --factory --port 8001)"""
from app.main import create_app

app = create_app()
