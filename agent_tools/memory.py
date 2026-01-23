import logging
from typing import Dict, Optional, Literal, Any
from langchain.tools import tool
from pydantic import BaseModel, Field
from langchain.memory import ConversationBufferMemory
from langchain_core.messages import SystemMessage

logger = logging.getLogger("tools")

# SAFETY CONFIGURATION
MAX_CONTENT_LENGTH = 4000 

class _ThreadMemoryRegistry:
    """
    Singleton registry to manage LangChain ConversationBufferMemory 
    instances per thread.
    """
    def __init__(self):
        self._registry: Dict[str, ConversationBufferMemory] = {}

    def get_memory(self, thread_id: str) -> ConversationBufferMemory:
        """Retrieves or creates a memory instance for the specific thread."""
        if thread_id not in self._registry:
            # return_messages=False ensures load_memory_variables returns a string 
            # (e.g., "Human: Hi\nAI: Hello") which is perfect for LLM context injection.
            self._registry[thread_id] = ConversationBufferMemory(
                memory_key="history",
                return_messages=False 
            )
        return self._registry[thread_id]

    def clear_memory(self, thread_id: str):
        """Clears the memory for a specific thread."""
        if thread_id in self._registry:
            self._registry[thread_id].clear()
            logger.info(f"🧹 Memory cleared for Thread ID: {thread_id}")

# Initialize the global registry
_memory_registry = _ThreadMemoryRegistry()


class ThreadMemoryInput(BaseModel):
    thread_id: str = Field(description="Unique thread/session identifier")
    action: Literal["read", "write", "reset"] = Field(
        description="Action to perform: 'read' retrieves history, 'write' adds to history, 'reset' wipes it."
    )
    content: Optional[str] = Field(
        default=None,
        description="The text content to write. Required for 'write' action."
    )
    role: Optional[Literal["user", "assistant", "system"]] = Field(
        default="user",
        description="Used only with 'write'. 'user' stores inputs, 'assistant' stores AI responses/context."
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
    role: str = "user",
) -> Dict[str, Any]:
    """
    Manages thread-scoped conversation memory.
    IMPORTANT: To retain full context, you must WRITE the User's query (role='user') 
    AND the AI's response (role='assistant') to this memory.
    """
    
    # Retrieve the specific memory instance for this thread
    memory = _memory_registry.get_memory(thread_id)

    try:
        if action == "read":
            # load_memory_variables returns a dict like {'history': 'Human: ... AI: ...'}
            data = memory.load_memory_variables({})
            history_text = data.get("history", "")
            
            return {
                "status": "success",
                "memory": history_text if history_text else "Memory is empty.",
            }

        if action == "write":
            if not content:
                return {
                    "status": "error",
                    "message": "content is required for write action",
                }
            
            # --- TRUNCATION LOGIC ---
            if len(content) > MAX_CONTENT_LENGTH:
                original_len = len(content)
                content = content[:MAX_CONTENT_LENGTH] + f"\n... [TRUNCATED from {original_len} chars] ..."
                logger.warning(f"⚠️ Memory write truncated for Thread {thread_id}.")

            # --- UPDATED CONTEXT LOGIC ---
            # We now distinguish between User inputs and AI outputs.
            # This ensures the 'read' action returns a coherent dialogue (Human vs AI).
            if role == "assistant":
                memory.chat_memory.add_ai_message(content)
                msg_type = "AI/Assistant"
            elif role == "system":
                # LangChain memory sometimes handles system messages differently, 
                # but adding it as a generic message helps context.
                memory.chat_memory.add_message(SystemMessage(content=content))
                msg_type = "System"
            else:
                # Default to user
                memory.chat_memory.add_user_message(content)
                msg_type = "User"
            
            return {
                "status": "success",
                "message": f"Successfully added {msg_type} message to memory.",
            }

        if action == "reset":
            # Before resetting, one might optionally log the summary, 
            # but the request is just to ensure context was known *before* this point.
            # The agent should have 'read' the memory before deciding to 'reset'.
            _memory_registry.clear_memory(thread_id)
            return {
                "status": "success",
                "message": "Memory reset successfully.",
            }

        return {
            "status": "error",
            "message": f"Unknown action: {action}",
        }

    except Exception as e:
        logger.error(f"Memory tool error: {str(e)}")
        return {
            "status": "error",
            "message": f"Internal memory error: {str(e)}",
        }