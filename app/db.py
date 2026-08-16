"""SQLite persistence for workflow definitions and execution history."""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .config import DATABASE_PATH


SENSITIVE_FIELD_NAMES = {
    "app_password",
    "password",
    "smtp_password",
    "authorization",
    "token",
    "secret",
}


def sanitize_for_storage(value: Any) -> Any:
    """Redact sensitive values before saving execution data."""

    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if key.lower() in SENSITIVE_FIELD_NAMES
                else sanitize_for_storage(item)
            )
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [sanitize_for_storage(item) for item in value]

    return value


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    """Open a connection that exposes rows as mapping-like objects."""

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    """Create the application's tables when they do not already exist."""

    schema = """
        CREATE TABLE IF NOT EXISTS workflows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            nodes TEXT NOT NULL,
            edges TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS workflow_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id INTEGER,
            status TEXT,
            input TEXT,
            output TEXT,
            error TEXT,
            started_at TEXT,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS node_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            node_id TEXT,
            node_type TEXT,
            status TEXT,
            input TEXT,
            output TEXT,
            error TEXT,
            started_at TEXT,
            completed_at TEXT
        );
    """

    with get_connection() as connection:
        connection.executescript(schema)


def create_workflow(
    name: str,
    description: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> int:
    """Persist a workflow and return its generated ID."""

    timestamp = utc_now()

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO workflows (
                name,
                description,
                nodes,
                edges,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                description,
                json.dumps(nodes),
                json.dumps(edges),
                timestamp,
                timestamp,
            ),
        )

        return int(cursor.lastrowid)


def get_workflow(workflow_id: int) -> dict[str, Any] | None:
    """Fetch one raw workflow row."""

    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM workflows WHERE id = ?",
            (workflow_id,),
        ).fetchone()

    return dict(row) if row else None


def list_workflows() -> list[dict[str, Any]]:
    """Fetch all raw workflow rows, newest first."""

    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM workflows ORDER BY id DESC"
        ).fetchall()

    return [dict(row) for row in rows]


def update_workflow(
    workflow_id: int,
    name: str,
    description: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> bool:
    """Replace a workflow definition and report whether it existed."""

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE workflows
            SET name = ?,
                description = ?,
                nodes = ?,
                edges = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                name,
                description,
                json.dumps(nodes),
                json.dumps(edges),
                utc_now(),
                workflow_id,
            ),
        )

        return cursor.rowcount > 0


def delete_workflow(workflow_id: int) -> bool:
    """Delete a workflow and its associated run records."""

    with get_connection() as connection:
        connection.execute(
            """
            DELETE FROM node_runs
            WHERE run_id IN (
                SELECT id FROM workflow_runs WHERE workflow_id = ?
            )
            """,
            (workflow_id,),
        )

        connection.execute(
            "DELETE FROM workflow_runs WHERE workflow_id = ?",
            (workflow_id,),
        )

        cursor = connection.execute(
            "DELETE FROM workflows WHERE id = ?",
            (workflow_id,),
        )

        return cursor.rowcount > 0


def create_run(workflow_id: int, input_data: dict[str, Any]) -> int:
    """Start a workflow run and return its generated ID."""

    safe_input = sanitize_for_storage(input_data)

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO workflow_runs (
                workflow_id,
                status,
                input,
                started_at
            )
            VALUES (?, 'RUNNING', ?, ?)
            """,
            (
                workflow_id,
                json.dumps(safe_input),
                utc_now(),
            ),
        )

        return int(cursor.lastrowid)


def finish_run(
    run_id: int,
    status: str,
    output: Any = None,
    error: str | None = None,
) -> None:
    """Record the terminal state of a workflow run."""

    safe_output = sanitize_for_storage(output)

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE workflow_runs
            SET status = ?,
                output = ?,
                error = ?,
                completed_at = ?
            WHERE id = ?
            """,
            (
                status,
                json.dumps(safe_output) if output is not None else None,
                error,
                utc_now(),
                run_id,
            ),
        )


def create_node_run(
    run_id: int,
    node_id: str,
    node_type: str,
    input_data: Any,
) -> int:
    """Start one node attempt and return its generated ID."""

    safe_input = sanitize_for_storage(input_data)

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO node_runs (
                run_id,
                node_id,
                node_type,
                status,
                input,
                started_at
            )
            VALUES (?, ?, ?, 'RUNNING', ?, ?)
            """,
            (
                run_id,
                node_id,
                node_type,
                json.dumps(safe_input),
                utc_now(),
            ),
        )

        return int(cursor.lastrowid)


def finish_node_run(
    node_run_id: int,
    status: str,
    output: Any = None,
    error: str | None = None,
) -> None:
    """Record the terminal state of a node attempt."""

    safe_output = sanitize_for_storage(output)

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE node_runs
            SET status = ?,
                output = ?,
                error = ?,
                completed_at = ?
            WHERE id = ?
            """,
            (
                status,
                json.dumps(safe_output) if output is not None else None,
                error,
                utc_now(),
                node_run_id,
            ),
        )


def list_runs(workflow_id: int) -> list[dict[str, Any]]:
    """List workflow runs, newest first."""

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM workflow_runs
            WHERE workflow_id = ?
            ORDER BY id DESC
            """,
            (workflow_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_run_detail(run_id: int) -> dict[str, Any] | None:
    """Fetch a workflow run together with all node attempt rows."""

    with get_connection() as connection:
        run = connection.execute(
            "SELECT * FROM workflow_runs WHERE id = ?",
            (run_id,),
        ).fetchone()

        node_runs = connection.execute(
            "SELECT * FROM node_runs WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()

    if not run:
        return None

    return {
        **dict(run),
        "node_runs": [dict(row) for row in node_runs],
    }