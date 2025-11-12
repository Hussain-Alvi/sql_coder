# api_endpoints/endpoints.py
from fastapi import APIRouter, File, Form, UploadFile, Request
import os, json, time

from data_validations.data_models import FrontendSendMessage, MessagesList, Message, Sender, UUIDRequest
from agents.sql_chat_agent import sql_agent

router = APIRouter()

# ✅ Helper: Save Chat History
def save_chat_history(uuid: str, settings, messages_history):
    if uuid not in messages_history:
        messages_history[uuid] = MessagesList()

    chat_history_file = os.path.join(settings.get("CHAT_HISTORY_PATH"), f"{uuid}_chat_history.json")

    with open(chat_history_file, "w") as f:
        json.dump(
            [{
                "text": msg.text,
                "sender": msg.sender.value
            } for msg in messages_history[uuid].messages_list],
            f, indent=4
        )


@router.post("/send_uuid")
async def send_uuid(data: UUIDRequest, request: Request):
    settings = request.app.state.settings
    messages_history = request.app.state.messages_history

    if data.uuid not in messages_history:
        messages_history[data.uuid] = MessagesList()

    welcome_message = "Hi! I’m your SQL assistant. Tell me what data you’d like to see, and I’ll query the database for you."
    messages_history[data.uuid].add_message(Message(sender=Sender.ASSISTANT, text=welcome_message))

    return {"welcome_message": welcome_message}


@router.post("/send_message")
async def send_message(message: FrontendSendMessage, request: Request):
    logger = request.app.state.logger
    settings = request.app.state.settings
    db_conn_str = request.app.state.db_conn_str
    messages_history = request.app.state.messages_history

    logger.info(f"\n\nMessage received:\n{message.uuid}: {message.text}")

    if message.uuid not in messages_history:
        messages_history[message.uuid] = MessagesList()

    messages_history[message.uuid].add_message(Message(sender=Sender.USER, text=message.text))

    start_time = time.time()
    reply = sql_agent(settings, logger, db_conn_str, messages_history[message.uuid])
    logger.info(f"Bot response execution took {time.time() - start_time:.2f} seconds")

    messages_history[message.uuid].add_message(Message(sender=Sender.ASSISTANT, text=reply))

    save_chat_history(message.uuid, settings, messages_history)

    return {"response": reply}


@router.post("/upload_audio")
async def upload_audio( request: Request, audio_file: UploadFile = File(...), uuid: str = Form(...)):
    logger = request.app.state.logger
    settings = request.app.state.settings
    messages_history = request.app.state.messages_history

    try:
        logger.info(f"\n\nAudio Message received:\n{uuid}")
        input_audio_file_path = os.path.join(
            settings.get("TEMP_INCOMING_AUDIO_PATH"),
            f"{uuid}_input_{len(messages_history[uuid].messages_list) + 1}.wav",
        )

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
