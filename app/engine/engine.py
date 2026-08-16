"""Workflow graph validation and sequential execution."""

import asyncio
from typing import Any

from .. import db
from ..nodes.builtin import NODE_REGISTRY


class WorkflowValidationError(Exception):
    """Raised when a workflow graph cannot be executed safely."""


def validate(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    """Validate the graph constraints currently supported by this engine."""

    node_ids = [node["id"] for node in nodes]
    if not nodes:
        raise WorkflowValidationError("Workflow must contain at least one node.")
    if len(node_ids) != len(set(node_ids)):
        raise WorkflowValidationError("Node IDs must be unique.")

    known_ids = set(node_ids)
    for edge in edges:
        if edge["source"] not in known_ids or edge["target"] not in known_ids:
            raise WorkflowValidationError(f"Invalid edge {edge['id']}.")
        if edge["source"] == edge["target"]:
            raise WorkflowValidationError("Self cycles are not supported.")

    for node in nodes:
        if node["type"] not in NODE_REGISTRY:
            raise WorkflowValidationError(f"Unsupported node type: {node['type']}")


def get_root_node_ids(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[str]:
    """Return nodes that do not have an incoming edge."""

    target_ids = {edge["target"] for edge in edges}
    return [node["id"] for node in nodes if node["id"] not in target_ids]


def get_outgoing_edges(node_id: str, edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return every edge leaving the given node."""

    return [edge for edge in edges if edge["source"] == node_id]


def get_node_input(
    node_id: str,
    edges: list[dict[str, Any]],
    context: dict[str, Any],
    last_output: Any,
) -> Any:
    """Select the direct input passed to a node.

    For root nodes this is the original execution input (`last_output` initially).
    For a normal linear path it is the upstream node output. Multi-parent joins are
    not yet merged; the final incoming edge in stored edge order is selected.
    """

    upstream_ids = [edge["source"] for edge in edges if edge["target"] == node_id]
    if not upstream_ids:
        return last_output

    upstream_output = context["nodes"].get(upstream_ids[-1], {}).get("output")
    return last_output if upstream_output is None else upstream_output


def get_selected_edges(
    node: dict[str, Any],
    result: Any,
    edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return outgoing edges allowed after a node completes."""

    outgoing = get_outgoing_edges(node["id"], edges)
    if node["type"] != "condition":
        return outgoing

    branch = result.get("branch") if isinstance(result, dict) else None
    return [
        edge
        for edge in outgoing
        if (edge.get("source_handle") or edge.get("sourceHandle")) == branch
    ]


async def execute_node(
    run_id: int,
    node: dict[str, Any],
    input_data: Any,
    context: dict[str, Any],
) -> Any:
    """Execute a single node with configured retry and timeout behavior."""

    config = node.get("config", {})
    retries = int(config.get("retries", 0))
    timeout = float(config.get("timeout", 60))
    node_class = NODE_REGISTRY[node["type"]]

    for attempt in range(retries + 1):
        node_run_id = db.create_node_run(run_id, node["id"], node["type"], input_data)
        try:
            result = await asyncio.wait_for(
                node_class().execute(input_data, config, context), timeout=timeout
            )
            db.finish_node_run(node_run_id, "COMPLETED", result)
            return result
        except Exception as exc:
            db.finish_node_run(node_run_id, "FAILED", error=str(exc))
            if attempt == retries:
                raise

    raise RuntimeError("Node retry loop ended unexpectedly.")


async def execute(workflow: dict[str, Any], input_data: dict[str, Any]) -> tuple[int, Any]:
    """Run a saved workflow and return its run ID plus final output."""

    nodes = workflow["nodes"]
    edges = workflow["edges"]
    validate(nodes, edges)

    run_id = db.create_run(workflow["id"], input_data)
    context: dict[str, Any] = {
        "input": input_data,
        "nodes": {},
        "variables": {},
        "workflow": {"id": workflow["id"], "name": workflow["name"]},
    }
    nodes_by_id = {node["id"]: node for node in nodes}
    queue = get_root_node_ids(nodes, edges)
    executed_node_ids: set[str] = set()
    last_output: Any = input_data

    try:
        if not queue:
            raise WorkflowValidationError("No starting node.")

        while queue:
            node_id = queue.pop(0)
            if node_id in executed_node_ids:
                continue

            node = nodes_by_id[node_id]
            node_input = get_node_input(node_id, edges, context, last_output)
            context["current"] = node_input

            result = await execute_node(run_id, node, node_input, context)
            context["nodes"][node_id] = {"output": result, "type": node["type"]}
            last_output = result
            executed_node_ids.add(node_id)

            for edge in get_selected_edges(node, result, edges):
                if edge["target"] not in executed_node_ids:
                    queue.append(edge["target"])

        db.finish_run(run_id, "COMPLETED", last_output)
        return run_id, last_output
    except Exception as exc:
        db.finish_run(run_id, "FAILED", error=str(exc))
        raise
