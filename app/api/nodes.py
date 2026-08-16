"""HTTP endpoint exposing available node types."""

from fastapi import APIRouter

from ..nodes.registry import all_nodes


router = APIRouter(prefix="/api/nodes", tags=["Nodes"])


@router.get("")
def list_nodes() -> list[dict[str, str]]:
    """Return metadata for every built-in node type."""

    return all_nodes()
