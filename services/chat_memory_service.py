# services/chat_memory_service.py
import json
import os
from typing import Dict, Any
from data_models.data_models import MessagesList, Message, Sender
from agent_tools.memory import thread_memory_manager


class ChatMemoryService:
    def __init__(self, settings: dict, logger: Any):
        self.settings = settings
        self.logger = logger
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

    def add_message(self, uuid: str, message: Message):
        """Adds a message to the in-memory history."""
        history = self.get_history(uuid)
        history.add_message(message)

    def initialize_chat(self, uuid: str) -> str:
        """Adds the welcome message if the chat is empty."""
        history = self.get_history(uuid)

        welcome_message = """Welcome to ITS Retails. I’m your AI Voice Assistant, here to help you access insights quickly. You can ask me to retrieve data from the database or perform online web searches to find relevant information for you."""

        if not any(msg.text == welcome_message for msg in history.messages_list):
            history.add_message(Message(sender=Sender.ASSISTANT, text=welcome_message))

        return welcome_message

    def save_history_to_disk(self, uuid: str):
        """Persists the current in-memory history to a JSON file."""
        if uuid not in self.messages_history:
            return

        chat_history_file = self._get_file_path(uuid)
        try:
            with open(chat_history_file, "w") as f:
                json.dump([{
                    "text": message.text,
                    "sender": message.sender.value
                } for message in self.messages_history[uuid].messages_list], f, indent=4)
            self.logger.info(f"Chat history for {uuid} saved successfully.")
        except Exception as e:
            self.logger.error(f"Failed to save chat history for {uuid}: {e}")

    def delete_history_file(self, uuid: str):
        """Deletes the physical JSON file."""
        chat_history_file = self._get_file_path(uuid)
        try:
            if os.path.exists(chat_history_file):
                os.remove(chat_history_file)
                self.logger.info(f"🗑️ Deleted persisted chat history for {uuid}")
        except Exception as e:
            self.logger.error(f"Failed to delete chat history for {uuid}: {e}")

    def is_reset_request(self, text: str) -> bool:
        """Analyzes text to see if the user wants to reset memory."""
        t = (text or "").strip().lower()
        phrases = {
            "reset", "reset chat", "reset memory", "clear memory", "clear chat",
            "forget", "forget everything", "start over", "start fresh", "wipe memory"
        }
        if t in phrases:
            return True
        return any(p in t for p in ["reset memory", "clear memory", "forget", "start over", "start fresh", "wipe"])

    def reset_session(self, uuid: str) -> str:
        """Performs the full reset: clears agent memory, clears RAM, deletes file."""
        self.logger.info(f"♻️ Reset requested. Clearing all state for {uuid}")

        thread_memory_manager.invoke({"thread_id": uuid, "action": "reset"})

        self.messages_history[uuid] = MessagesList()

        self.delete_history_file(uuid)

        reply_text = "Memory has been reset successfully." + " memory-reset"
        self.add_message(uuid, Message(sender=Sender.ASSISTANT, text=reply_text))

        self.save_history_to_disk(uuid)

        return reply_text