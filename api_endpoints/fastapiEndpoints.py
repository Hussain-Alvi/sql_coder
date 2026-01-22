import json
import os
import time
from typing import Dict
from fastapi import APIRouter, UploadFile, File, Form
from agents.agent import sql_agent
from data_models.data_models import FrontendSendMessage, MessagesList, Message, Sender, UUIDRequest
from utilities.utils import get_settings, get_logger, get_db_connection

router = APIRouter()
settings = get_settings()
logger = get_logger(settings)
db_conn_str: str = get_db_connection(settings, logger)
messages_history: Dict[str, MessagesList] = {}


def save_chat_history(uuid: str):
    if uuid not in messages_history:
        messages_history[uuid] = MessagesList()

    chat_history_path = settings.get("CHAT_HISTORY_PATH", "chat_histories")
    if not os.path.exists(chat_history_path):
        os.makedirs(chat_history_path)
    
    chat_history_file = os.path.join(chat_history_path, f"{uuid}_chat_history.json")

    try:
        with open(chat_history_file, "w") as f:
            json.dump([{
                "text": message.text,
                "sender": message.sender.value
            } for message in messages_history[uuid].messages_list], f, indent=4)
        logger.info(f"Chat history for {uuid} saved successfully.")
    except Exception as e:
        logger.error(f"Failed to save chat history for {uuid}: {e}")


@router.post("/send_uuid")
async def send_uuid(data: UUIDRequest):
    global messages_history
    if data.uuid not in messages_history:
        messages_history[data.uuid] = MessagesList()

    welcome_message = """Welcome to ITS Retails.
                         I’m your AI Voice Assistant, here to help you access insights quickly. 
                         You can ask me to retrieve data from the database or perform online web searches to find relevant information for you."""
    
    # Only add welcome message if the history is empty or it's not already there
    if not any(msg.text == welcome_message for msg in messages_history[data.uuid].messages_list):
        messages_history[data.uuid].add_message(Message(sender=Sender.ASSISTANT, text=welcome_message))

    return {"welcome_message": welcome_message}


@router.post("/send_message")
async def send_message(message: FrontendSendMessage):
    
    logger.info(f"\n\nMessage received:\n{message.uuid}: {message.text}")

    global messages_history
    
    # Ensure history list exists
    if message.uuid not in messages_history:
        messages_history[message.uuid] = MessagesList()

    # Add User Message to History
    messages_history[message.uuid].add_message(Message(sender=Sender.USER, text=message.text))

    start_time = time.time()
    
    # ---------------------------------------------------------
    # Call Agent (Logic moved to Agent/Decide Tool)
    # ---------------------------------------------------------
    reply = sql_agent(
        settings, 
        logger, 
        db_conn_str, 
        messages_history[message.uuid],
        thread_id=message.uuid 
    )
    
    elapsed_time = time.time() - start_time
    logger.info(f"Bot response execution took {elapsed_time:.2f} seconds")

    # ---------------------------------------------------------
    # Sync Logic: Clear Local History if Agent Reset Memory
    # ---------------------------------------------------------
    # The agent returns this specific phrase when 'reset_memory' tool is triggered.
    # We must clear the local messages_history so we don't send old context next time.
    if "Memory has been reset successfully" in reply:
        logger.info(f"♻️ Agent triggered reset. Clearing local history for {message.uuid}")
        messages_history[message.uuid] = MessagesList()
        # Add the agent's confirmation as the only message in the new history
        messages_history[message.uuid].add_message(Message(sender=Sender.ASSISTANT, text=reply))
    else:
        # Standard flow: Append agent reply to history
        messages_history[message.uuid].add_message(Message(sender=Sender.ASSISTANT, text=reply))

    logger.info(f"Response sent:\n{reply}")
    
    # Save history to disk--
    save_chat_history(message.uuid)

    return {"response": reply}

@router.post("/upload_audio")
async def upload_audio(audio_file: UploadFile = File(...), uuid: str = Form(...)):

    try:
        logger.info(f"\n\nAudio Message received from: {uuid}")

        temp_audio_path = settings.get("TEMP_INCOMING_AUDIO_PATH", "temp_audio")
        if not os.path.exists(temp_audio_path):
            os.makedirs(temp_audio_path)

        if uuid not in messages_history:
            messages_history[uuid] = MessagesList()

        file_number = len(messages_history[uuid].messages_list) + 1
        input_audio_file_path = os.path.join(temp_audio_path, f"{uuid}_input_{file_number}.wav")

        with open(input_audio_file_path, "wb") as f:
            f.write(await audio_file.read())
        
        logger.info(f"Audio for {uuid} saved to {input_audio_file_path}")

        return {
            "message": "Audio uploaded successfully",
            "uuid": uuid,
            "file_path": input_audio_file_path,
        }
    except Exception as e:
        logger.error(f"Error saving audio for UUID {uuid}: {e}")
        return {"error": str(e), "uuid": uuid}