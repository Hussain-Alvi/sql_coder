import logging
from typing import Dict, Optional, Literal
from langchain.tools import tool
from pydantic import BaseModel, Field


logger = logging.getLogger("tools")

class _ThreadMemoryStore:
    """In-memory thread-scoped short-term memory."""
    def __init__(self):
        self._store: Dict[str, list[str]] = {}

    def get(self, thread_id: str):
        return self._store.get(thread_id, [])

    def append(self, thread_id: str, value: str):
        self._store.setdefault(thread_id, []).append(value)

    def reset(self, thread_id: str):
        self._store[thread_id] = []
        # Explicitly log this action to verify the fix
        logger.info(f"🧹 Internal Memory Store cleared for Thread ID: {thread_id}")


_thread_memory_store = _ThreadMemoryStore()


class ThreadMemoryInput(BaseModel):
    thread_id: str = Field(description="Unique thread/session identifier")
    action: Literal["read", "write", "reset"] = Field(
        description="Action to perform on memory"
    )
    content: Optional[str] = Field(
        default=None,
        description="Content to write (required for write)"
    )


@tool(
    "thread_memory_manager",
    args_schema=ThreadMemoryInput,
    return_direct=False,
)
def thread_memory_manager(
    thread_id: str,
    action: str,
    content: Optional[str] = None,
):
    """Manages thread-scoped short-term memory."""

    if action == "read":
        return {
            "status": "success",
            "memory": _thread_memory_store.get(thread_id),
        }

    if action == "write":
        if not content:
            return {
                "status": "error",
                "message": "content is required for write action",
            }
        _thread_memory_store.append(thread_id, content)
        return {
            "status": "success",
            "message": "memory updated",
        }

    if action == "reset":
        _thread_memory_store.reset(thread_id)
        return {
            "status": "success",
            "message": "memory reset",
        }

    return {
        "status": "error",
        "message": f"Unknown action: {action}",
    }
