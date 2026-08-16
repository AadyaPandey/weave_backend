"""Built-in workflow templates and graph construction helpers."""

from typing import Any


TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "text-summarizer", "name": "Text Summarizer", "description": "Text -> LLM -> Response",
        "nodes": [
            ("input", "text", {"text": "{{input.text}}"}),
            ("llm", "llm", {"prompt": "Summarize in 5 bullet points:\n{{nodes.input.output.text}}"}),
            ("output", "response", {"value": "{{nodes.llm.output.output}}"}),
        ],
    },
    {
        "id": "customer-support", "name": "AI Customer Support", "description": "LLM + IF branching",
        "nodes": [
            ("input", "text", {"text": "{{input.message}}"}),
            ("llm", "llm", {"prompt": "Analyze this customer message and reply:\n{{nodes.input.output.text}}"}),
            ("condition", "condition", {"left": "{{nodes.llm.output.output}}", "operator": "contains", "right": "negative"}),
            ("standard", "response", {"value": "{{nodes.llm.output.output}}"}),
            ("urgent", "response", {"value": "Escalate: {{nodes.llm.output.output}}"}),
        ],
    },
    {
        "id": "email-classifier", "name": "Email Classifier", "description": "Classify email with LLM",
        "nodes": [
            ("input", "text", {"text": "{{input.email}}"}),
            ("llm", "llm", {"prompt": "Classify as Sales, Support, Complaint, Spam, or Other:\n{{nodes.input.output.text}}"}),
            ("output", "response", {"value": "{{nodes.llm.output.output}}"}),
        ],
    },
    {
        "id": "api-data-processor", "name": "API Data Processor", "description": "HTTP -> Transform -> Response",
        "nodes": [
            ("request", "http_request", {"method": "GET", "url": "{{input.url}}"}),
            ("transform", "transform", {"operation": "identity", "value": "{{nodes.request.output.data}}"}),
            ("output", "response", {"value": "{{nodes.transform.output}}"}),
        ],
    },
    {
        "id": "resume-analyzer", "name": "Resume Analyzer", "description": "Resume + job description -> LLM",
        "nodes": [
            ("resume", "text", {"text": "{{input.resume}}"}),
            ("llm", "llm", {"prompt": "Score this resume against the job description:\nRESUME:\n{{nodes.resume.output.text}}\nJOB:\n{{input.job_description}}"}),
            ("output", "response", {"value": "{{nodes.llm.output.output}}"}),
        ],
    },
    {
        "id": "invoice-analyzer", "name": "Invoice Analyzer", "description": "Invoice -> LLM extraction",
        "nodes": [
            ("invoice", "text", {"text": "{{input.invoice}}"}),
            ("llm", "llm", {"prompt": "Extract merchant,total,tax,date,currency as JSON:\n{{nodes.invoice.output.text}}"}),
            ("output", "response", {"value": "{{nodes.llm.output.output}}"}),
        ],
    },
    {
        "id": "text-to-email",
        "name": "Text to Email",
        "description": "Convert text into a professional email with LLM and send it",
        "nodes": [
            (
                "input",
                "text",
                {
                    "text": "{{input.text}}",
                },
            ),
            (
                "llm",
                "llm",
                {
                    "prompt": (
                        "Convert the following text into a professional email body. "
                        "Return only the email body without a subject line.\n\n"
                        "{{nodes.input.output.text}}"
                    ),
                },
            ),
            (
                "email",
                "email",
                {
                    "sender_email": "{{input.email_send.sender_email}}",
                    "app_password": "{{input.email_send.app_password}}",
                    "to": "{{input.email_send.to}}",
                    "subject": "{{input.email_send.subject}}",
                    "body": "{{nodes.llm.output.output}}",
                    "smtp_host": "smtp.gmail.com",
                    "smtp_port": 587,
                    "smtp_use_tls": True,
                },
            ),
            (
                "output",
                "response",
                {
                    "value": "{{nodes.email.output}}",
                },
            ),
        ],
    },
]


def list_templates() -> list[dict[str, str]]:
    """Return compact template metadata."""

    return [{key: template[key] for key in ("id", "name", "description")} for template in TEMPLATES]


def get_template(template_id: str) -> dict[str, Any] | None:
    """Find one template definition by ID."""

    return next((template for template in TEMPLATES if template["id"] == template_id), None)


def build_template_graph(template: dict[str, Any]) -> dict[str, Any]:
    """Construct API-ready node and edge dictionaries for a template."""

    nodes = [{"id": node_id, "type": node_type, "config": config} for node_id, node_type, config in template["nodes"]]
    if template["id"] == "customer-support":
        edges = [
            {"id": "e1", "source": "input", "target": "llm"},
            {"id": "e2", "source": "llm", "target": "condition"},
            {"id": "e3", "source": "condition", "target": "standard", "source_handle": "false"},
            {"id": "e4", "source": "condition", "target": "urgent", "source_handle": "true"},
        ]
    else:
        edges = [
            {"id": f"e{index}", "source": nodes[index - 1]["id"], "target": nodes[index]["id"]}
            for index in range(1, len(nodes))
        ]
    return {"id": template["id"], "name": template["name"], "description": template["description"], "nodes": nodes, "edges": edges}
