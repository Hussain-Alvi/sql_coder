""""Fast API class."""
import json
import os
import time
from typing import Dict, List
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from data_models import FrontendSendMessage, MessagesList, Message, Sender, UUIDRequest
from sql_chat_agent import sql_agent
from utils import get_settings, get_logger, get_db_connection

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with specific allowed origins if needed
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

settings = get_settings()
logger = get_logger(settings)
db_conn_str: str = get_db_connection(settings, logger)
messages_history: Dict[str, MessagesList] = {}


def save_chat_history(uuid: str):
    """
    Saves the chat history for a given UUID to a JSON file.

    Args:
        uuid (str): The unique identifier for the chat session.

    This function retrieves the chat history from the `messages_history` dictionary using the provided UUID,
    and writes the message list into a JSON file. Each message is represented as a dictionary with the message text
    and the sender (either 'User' or 'ASSISTANT'). The JSON file is saved with the name format `{uuid}_chat_history.json`
    in the directory specified by the `CHAT_HISTORY_PATH` setting.

    The method ensures that enum values of the `Sender` type are serialized to their string representation.

    Raises:
        KeyError: If the UUID does not exist in the `messages_history` dictionary.
    """
    # Ensure the uuid exists to avoid KeyError when saving
    if uuid not in messages_history:
        messages_history[uuid] = MessagesList()

    chat_history_file = os.path.join(settings.get("CHAT_HISTORY_PATH"), f"{uuid}_chat_history.json")

    # Convert MessagesList to a list of dictionaries for saving as JSON
    # Ensure that Sender is converted to its string value using .value
    with open(chat_history_file, "w") as f:
        json.dump([{
            "text": message.text,
            "sender": message.sender.value  # Convert enum to string
        } for message in messages_history[uuid].messages_list], f, indent=4)


@app.post("/send_uuid")
async def send_uuid(data: UUIDRequest):
    global messages_history
    # Check if the UUID exists in the history, if not, initialize it
    if data.uuid not in messages_history:
        messages_history[data.uuid] = MessagesList()

    welcome_message = "Hi! I’m your SQL assistant. Tell me what data you’d like to see, and I’ll query the database for you."
    messages_history[data.uuid].add_message(Message(sender=Sender.ASSISTANT, text=welcome_message))

    return {"welcome_message": welcome_message}


@app.post("/send_message")
async def send_message(message: FrontendSendMessage, request: Request):
    """
    Handles incoming user messages and returns a response from the AI Psychotherapist.

    Args:
        message (FrontendSendMessage): The incoming message from the frontend, which contains the message text and UUID.
        request (Request): The FastAPI request object (automatically provided by FastAPI).
    """
    logger.info(f"\n\nMessage received:\n{message.uuid}: {message.text}")

    global messages_history
    global db_conn_str

    # Ensure the uuid exists before accessing it to prevent KeyError
    if message.uuid not in messages_history:
        messages_history[message.uuid] = MessagesList()

    messages_history[message.uuid].add_message(Message(sender=Sender.USER, text=message.text))

    # reply = message.text + " (processed)"  # temp reply
    start_time = time.time()
    reply = sql_agent(settings, logger, db_conn_str, messages_history[message.uuid])
    elapsed_time = time.time() - start_time
    logger.info(f"Bot response execution took {elapsed_time:.2f} seconds")

    messages_history[message.uuid].add_message(Message(sender=Sender.ASSISTANT, text=reply))

    logger.info(f"Response sent:\n{reply}")

    save_chat_history(message.uuid)

    return {"response": reply}




# ✅ NEW ENDPOINT: Upload and store audio locally
@app.post("/upload_audio")
async def upload_audio(file: UploadFile = File(...)):
    """
    Endpoint to receive an audio recording and store it locally.
    Accepts a recorded audio clip (e.g., WAV, MP3) and saves it in 'uploaded_audios/'.
    """
    try:
        upload_dir = "uploaded_audios"
        os.makedirs(upload_dir, exist_ok=True)

        file_path = os.path.join(upload_dir, file.filename)

        # Save uploaded audio file
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())

        logger.info(f"Audio file saved: {file_path}")
        return {"message": "Audio uploaded successfully", "file_path": file_path}
    except Exception as e:
        logger.error(f"Error saving audio: {e}")
        return {"error": str(e)}



if __name__ == "__main__":
    uvicorn.run(app, host=settings.get("SERVER_IP"), port=settings.get("SERVER_PORT"))
