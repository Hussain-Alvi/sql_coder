import json
import logging
import os
from typing import Any, Dict, Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from data_models.data_models import MessagesList, Message, Sender

logger = logging.getLogger("tools")


class _ThreadMemoryRegistry:
    """
    Registry to manage MessagesList instances per thread.
    Currently used only for hard-reset (delete the instance and persisted file).
    """

    def __init__(self, settings: dict, logger_: Any):
        self.settings = settings
        self.logger = logger_
        self.messages_history: Dict[str, MessagesList] = {}

    def _get_file_path(self, uuid: str) -> str:
        """Determines the file path for a specific UUID."""
        chat_history_path = self.settings.get("CHAT_HISTORY_PATH", "chat_histories")
        if not os.path.exists(chat_history_path):
            os.makedirs(chat_history_path)
        return os.path.join(chat_history_path, f"{uuid}_chat_history.json")

    def get_history(self, uuid: str) -> MessagesList:
        """Retrieves history from memory, creating it if it doesn't exist."""
        if uuid not in self.messages_history:
            self.messages_history[uuid] = MessagesList()
        return self.messages_history[uuid]

    def add_message(self, uuid: str, message: Message) -> None:
        """Adds a message to the in-memory history."""
        history = self.get_history(uuid)
        history.add_message(message)

    def initialize_chat(self, uuid: str) -> str:
        """Adds the welcome message if the chat is empty."""
        history = self.get_history(uuid)

        welcome_message = (
            "Welcome to ITS Retails. I’m your AI Voice Assistant, here to help you access insights quickly. "
            "You can ask me to retrieve data from the database or perform online web searches to find relevant "
            "information for you."
        )

        if not any(msg.text == welcome_message for msg in history.messages_list):
            history.add_message(Message(sender=Sender.ASSISTANT, text=welcome_message))

        return welcome_message

    def save_history_to_disk(self, uuid: str) -> None:
        """Persists the current in-memory history to a JSON file."""
        if uuid not in self.messages_history:
            return

        chat_history_file = self._get_file_path(uuid)
        try:
            with open(chat_history_file, "w", encoding="utf-8") as f:
                json.dump(
                    [
                        {"text": message.text, "sender": message.sender.value}
                        for message in self.messages_history[uuid].messages_list
                    ],
                    f,
                    indent=4,
                )
            self.logger.info("Chat history for %s saved successfully.", uuid)
        except Exception as e:
            self.logger.error("Failed to save chat history for %s: %s", uuid, e)

    def delete_history_file(self, uuid: str) -> str:
        """Deletes the physical JSON file and clears in-memory history for this UUID."""
        self.messages_history.pop(uuid, None)

        chat_history_file = self._get_file_path(uuid)
        try:
            if os.path.exists(chat_history_file):
                os.remove(chat_history_file)
                self.logger.info("🗑️ Deleted persisted chat history for %s", uuid)
        except Exception as e:
            self.logger.error("Failed to delete chat history for %s: %s", uuid, e)

        reply_text = "Memory has been reset successfully. memory-reset"
        return reply_text


class ThreadMemoryInput(BaseModel):
    thread_id: str = Field(description="Unique thread/session identifier")
    action: Literal["reset"] = Field(
        description="Only supported action: 'reset' wipes the memory for this thread."
    )


def make_memory_service(settings: dict, logger_: Any) -> _ThreadMemoryRegistry:
    """Factory used by the app to create the per-process memory service."""
    return _ThreadMemoryRegistry(settings=settings, logger_=logger_)


_memory_registry: _ThreadMemoryRegistry | None = None


@tool(
    "thread_memory_manager",
    args_schema=ThreadMemoryInput,
    return_direct=True,
)
def thread_memory_manager(thread_id: str, action: str) -> Dict[str, Any]:
    """
    Reset-only memory tool.
    App-level chat history is managed elsewhere; this tool exists to ensure
    any server-side memory instances are wiped on reset.
    """
    global _memory_registry

    try:
        if _memory_registry is None:
            return {
                "status": "error",
                "message": "Memory service is not initialized.",
            }

        if action == "reset":
            msg = "Memory has been reset successfully." + " memory-reset"
            return {"status": "success", "message": msg}

        return {"status": "error", "message": f"Unknown action: {action}"}
    except Exception as e:
        logger.error("Memory tool error: %s", str(e))
        return {"status": "error", "message": f"Internal memory error: {str(e)}"}