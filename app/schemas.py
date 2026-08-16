"""Request and response-shaped schemas used by the workflow API."""

from typing import Any

from pydantic import BaseModel, Field


class Node(BaseModel):
    """A configured unit of work in a workflow graph."""

    id: str
    type: str
    config: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, float] = Field(default_factory=dict)


class Edge(BaseModel):
    """A directed connection from one node to another."""

    id: str
    source: str
    target: str
    source_handle: str | None = None
    target_handle: str | None = None


class WorkflowCreate(BaseModel):
    """Payload used to create or replace a workflow."""

    name: str
    description: str = ""
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)


class ExecuteRequest(BaseModel):
    """Caller-provided data for a workflow run."""

    input: dict[str, Any] = Field(default_factory=dict)
