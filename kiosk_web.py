"""Compatibility wrapper: the project now runs as a single FastAPI application.
The legacy kiosk script is kept only for backwards compatibility and redirects to the
same app instance so Railway deployments don't depend on a second service.
"""

from app.main import app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
