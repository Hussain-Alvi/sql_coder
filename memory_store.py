# memory_store.py
from langchain.memory import ConversationBufferMemory
from langchain.schema import HumanMessage, AIMessage
from typing import Dict
from db_ops import history_collection

# runtime memory store
session_memories: Dict[str, ConversationBufferMemory] = {}

def get_or_create_memory(session_id: str):
    """Load memory from cache or MongoDB if missing."""
    if session_id in session_memories:
        return session_memories[session_id]

    memory = ConversationBufferMemory(memory_key="history", input_key="user_input")

    # restore past conversation from Mongo
    past_logs = history_collection.find({"session_id": session_id}).sort("timestamp", 1)
    for log in past_logs:
        if log.get("user_input"):
            memory.chat_memory.add_message(HumanMessage(content=log["user_input"]))
        if log.get("response"):
            memory.chat_memory.add_message(AIMessage(content=log["response"]))

    session_memories[session_id] = memory
    return memory
