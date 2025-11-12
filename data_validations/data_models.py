from enum import Enum
from typing import List

from pydantic import BaseModel


class UUIDRequest(BaseModel):
    """Frontend to FastAPi uuid receiver model."""
    uuid: str


class FrontendSendMessage(BaseModel):
    """Frontend to FastAPi message receiver model."""
    text: str
    uuid: str


class Sender(Enum):
    USER = "User"
    ASSISTANT = "Assistant"


class Message(BaseModel):
    text: str
    sender: Sender


class MessagesList(BaseModel):
    messages_list: List[Message] = []

    def add_message(self, message: Message):
        """Add a new message to the messages list."""
        self.messages_list.append(message)

    def __str__(self):
        """Return a string representation of the messages list."""
        return "\n".join(f"{msg.sender.value}: {msg.text}" for msg in self.messages_list)
