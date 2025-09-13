# app/main.py
import html

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute

from app.api.health import router as health_router
from app.api.markets import router as markets_router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

# CORS
origins = [o.strip() for o in (settings.CORS_ORIGINS or "").split(",") if o.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )


@app.get("/", include_in_schema=False)
def root():
    links = [
        {"rel": "docs", "href": "/docs"},
        # {"rel": "redoc", "href": "/redoc"},
        {"rel": "health", "href": "/health"},
        {"rel": "markets", "href": "/markets"},
    ]

    # auto-list other GET routes (skip internals and param routes)
    skip = {"/", "/docs", "/openapi.json", "/health", "/markets"}
    for route in app.routes:
        if isinstance(route, APIRoute) and "GET" in route.methods:
            path = route.path
            if path not in skip and "{" not in path:
                links.append({"rel": "get", "href": path})

    return {
        "ok": True,
        "service": "sokomjinga-api",
        "message": "See /docs for full API documentation.",
        "links": links,
    }


# Routers
app.include_router(health_router)
app.include_router(markets_router, prefix="/markets", tags=["markets"])
