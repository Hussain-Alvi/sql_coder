import logging
from typing import Dict, Literal, Any
from langchain.tools import tool
from pydantic import BaseModel, Field
from langchain.memory import ConversationBufferMemory

logger = logging.getLogger("tools")

class _ThreadMemoryRegistry:
    """
    Singleton registry to manage ConversationBufferMemory instances per thread.
    Currently used only for hard-reset (delete the instance).
    """
    def __init__(self):
        self._registry: Dict[str, ConversationBufferMemory] = {}

    def delete_memory(self, thread_id: str) -> bool:
        existed = thread_id in self._registry
        if existed:
            self._registry.pop(thread_id, None)
            logger.info(f"♻️ Memory instance deleted for Thread ID: {thread_id}")
        return existed

_memory_registry = _ThreadMemoryRegistry()

class ThreadMemoryInput(BaseModel):
    thread_id: str = Field(description="Unique thread/session identifier")
    action: Literal["reset"] = Field(description="Only supported action: 'reset' wipes the memory for this thread.")

@tool(
    "thread_memory_manager",
    args_schema=ThreadMemoryInput,
    return_direct=False,
)
def thread_memory_manager(thread_id: str, action: str) -> Dict[str, Any]:
    """
    Reset-only memory tool.
    App-level chat history is managed elsewhere; this tool exists to ensure
    any server-side memory instances are wiped on reset.
    """
    try:
        if action == "reset":
            _memory_registry.delete_memory(thread_id)
            return {"status": "success", "message": "Memory reset successfully."}

        return {"status": "error", "message": f"Unknown action: {action}"}
    except Exception as e:
        logger.error(f"Memory tool error: {str(e)}")
        return {"status": "error", "message": f"Internal memory error: {str(e)}"}