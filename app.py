""""Fast API class."""
import json
import os
import time
from typing import Dict, List
from fastapi import FastAPI, Request, UploadFile, File, Form
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

# ✅ FINAL UPDATED ENDPOINT — using your provided logic
@app.post("/upload_audio")
async def upload_audio(audio_file: UploadFile = File(...), uuid: str = Form(...)):
    """
    Endpoint to receive an audio recording and store it locally with associated UUID.
    Audio is saved in TEMP_INCOMING_AUDIO_PATH with the format: {uuid}input{N}.wav
    """
    try:
        logger.info(f"\n\nAudio Message received:\n{uuid}")
        input_audio_file_path = os.path.join(
            settings.get("TEMP_INCOMING_AUDIO_PATH"),
            f"{uuid}_input_{len(messages_history[uuid].messages_list) + 1}.wav",
        )  # wav/webm
        # Save the uploaded audio file temporarily
        with open(input_audio_file_path, "wb") as f:
            f.write(await audio_file.read())

        return {
            "message": "Audio uploaded successfully",
            "uuid": uuid,
            "file_path": input_audio_file_path,
        }

    except Exception as e:
        logger.error(f"Error saving audio for UUID {uuid}: {e}")
        return {"error": str(e), "uuid": uuid}

if __name__ == "__main__":
    uvicorn.run(app, host=settings.get("SERVER_IP"), port=settings.get("SERVER_PORT"))
