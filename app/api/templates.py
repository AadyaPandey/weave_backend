"""HTTP endpoints for built-in workflow templates."""

from typing import Any

from fastapi import APIRouter, HTTPException

from .. import db
from ..templates.templates import build_template_graph, get_template, list_templates


router = APIRouter(prefix="/api/templates", tags=["Templates"])


def require_template(template_id: str) -> dict[str, Any]:
    """Fetch a template or raise a consistent 404 response."""

    template = get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.get("")
def list_available_templates() -> list[dict[str, str]]:
    """List starter templates."""

    return list_templates()


@router.get("/{template_id}")
def get_template_graph(template_id: str) -> dict[str, Any]:
    """Return the complete graph for a starter template."""

    return build_template_graph(require_template(template_id))


@router.post("/{template_id}/use")
def use_template(template_id: str) -> dict[str, Any]:
    """Persist a starter template as a new editable workflow."""

    graph = build_template_graph(require_template(template_id))
    workflow_id = db.create_workflow(
        graph["name"], graph["description"], graph["nodes"], graph["edges"]
    )
    return {"workflow_id": workflow_id, "template_id": template_id}
