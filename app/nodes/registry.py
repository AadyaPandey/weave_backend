"""UI-facing metadata for the built-in node registry."""

from .builtin import NODE_REGISTRY


NODE_METADATA: dict[str, tuple[str, str, str]] = {
    "manual_trigger": ("Manual Trigger", "Trigger", "Starts a workflow manually"),
    "text": ("Text Input", "Input", "Provides text"),
    "json": ("JSON Input", "Input", "Provides structured JSON"),
    "llm": ("LLM", "AI", "Generate text with an LLM"),
    "http_request": ("HTTP Request", "API", "Call an external HTTP API"),
    "weather": ("Weather Lookup", "Tool", "Gets current weather from Open-Meteo"),
    "email": ("Send Email", "Tool", "Sends an email through SMTP"),
    "condition": ("IF", "Logic", "Choose a true/false branch"),
    "transform": ("Transform", "Utility", "Transform data"),
    "response": ("Response", "Output", "Return a workflow result"),
}


def all_nodes() -> list[dict[str, str]]:
    """Return serializable node-palette metadata."""

    return [
        {"type": node_type, "name": name, "category": category, "description": description}
        for node_type, (name, category, description) in NODE_METADATA.items()
        if node_type in NODE_REGISTRY
    ]
