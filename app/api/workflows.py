"""HTTP endpoints for managing and executing workflows."""

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from .. import db
from ..engine.engine import execute, validate
from ..schemas import ExecuteRequest, WorkflowCreate


router = APIRouter(prefix="/api/workflows", tags=["Workflows"])


def serialize_workflow(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw SQLite workflow row into an API response."""

    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "nodes": json.loads(row["nodes"]),
        "edges": json.loads(row["edges"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def payload_parts(payload: WorkflowCreate) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert Pydantic node and edge models to persistence-ready dictionaries."""

    return (
        [node.model_dump() for node in payload.nodes],
        [edge.model_dump() for edge in payload.edges],
    )


def validate_payload(payload: WorkflowCreate) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate a workflow request or raise a useful HTTP error."""

    nodes, edges = payload_parts(payload)
    try:
        validate(nodes, edges)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return nodes, edges


@router.post("")
def create_workflow(payload: WorkflowCreate) -> dict[str, Any]:
    """Validate and persist a new workflow."""

    nodes, edges = validate_payload(payload)
    workflow_id = db.create_workflow(payload.name, payload.description, nodes, edges)
    return serialize_workflow(db.get_workflow(workflow_id))


@router.get("")
def list_workflows() -> list[dict[str, Any]]:
    """List all saved workflows."""

    return [serialize_workflow(row) for row in db.list_workflows()]


@router.get("/runs/{run_id}")
def get_run(run_id: int) -> dict[str, Any]:
    """Return a run and its per-node attempt history."""

    run = db.get_run_detail(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    for key in ("input", "output"):
        if run.get(key):
            try:
                run[key] = json.loads(run[key])
            except (TypeError, json.JSONDecodeError):
                pass
    return run


@router.get("/{workflow_id}/runs")
def get_workflow_history(workflow_id: int) -> list[dict[str, Any]]:
    """List prior runs for a workflow."""

    if not db.get_workflow(workflow_id):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return db.list_runs(workflow_id)


@router.get("/{workflow_id}")
def get_workflow(workflow_id: int) -> dict[str, Any]:
    """Fetch one saved workflow."""

    workflow = db.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return serialize_workflow(workflow)


@router.put("/{workflow_id}")
def update_workflow(workflow_id: int, payload: WorkflowCreate) -> dict[str, Any]:
    """Validate and replace a workflow definition."""

    nodes, edges = validate_payload(payload)
    updated = db.update_workflow(workflow_id, payload.name, payload.description, nodes, edges)
    if not updated:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return serialize_workflow(db.get_workflow(workflow_id))


@router.delete("/{workflow_id}")
def delete_workflow(workflow_id: int) -> dict[str, Any]:
    """Delete a workflow and its execution history."""

    if not db.delete_workflow(workflow_id):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"deleted": True, "workflow_id": workflow_id}


@router.post("/{workflow_id}/execute")
async def run_workflow(workflow_id: int, payload: ExecuteRequest) -> dict[str, Any]:
    """Execute a saved workflow with caller-provided input."""

    workflow = db.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    try:
        run_id, output = await execute(serialize_workflow(workflow), payload.input)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Workflow execution failed: {exc}"
        ) from exc
    return {"run_id": run_id, "status": "COMPLETED", "output": output}
