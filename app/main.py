"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.nodes import router as nodes_router
from .api.templates import router as templates_router
from .api.workflows import router as workflows_router
from .db import init_db
from .nodes.builtin import NODE_REGISTRY


app = FastAPI(
    title="Weave API",
    version="1.1.0",
    description="n8n-style workflow automation backend",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    """Ensure persistence is ready before accepting requests."""

    init_db()


@app.get("/health", tags=["System"])
def health() -> dict[str, object]:
    """Return a lightweight service-health response."""

    return {"status": "ok", "nodes": sorted(NODE_REGISTRY)}


app.include_router(workflows_router)
app.include_router(nodes_router)
app.include_router(templates_router)
