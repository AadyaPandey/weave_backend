"""Contract implemented by every workflow node."""

from abc import ABC, abstractmethod
from typing import Any


class BaseNode(ABC):
    """A unit of work that can run inside a workflow execution."""

    @abstractmethod
    async def execute(
        self,
        input_data: Any,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> Any:
        """Run the node and return a serializable output."""
