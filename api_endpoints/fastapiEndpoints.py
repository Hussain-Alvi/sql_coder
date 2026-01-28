import json
import os
import time
from fastapi import APIRouter, UploadFile, File, Form

# Internal Imports
from agents.router_agent import master_router_agent
from data_models.data_models import FrontendSendMessage, Message, Sender, UUIDRequest
from utilities.utils import get_settings, get_logger, get_db_connection
from services.chat_memory_service import ChatMemoryService

router = APIRouter()
settings = get_settings()
logger = get_logger(settings)
db_conn_str: str = get_db_connection(settings, logger)

memory_service = ChatMemoryService(settings, logger)

@router.post("/send_uuid")
async def send_uuid(data: UUIDRequest):
    welcome_msg = memory_service.initialize_chat(data.uuid)
    return {"welcome_message": welcome_msg}

@router.post("/send_message")
async def send_message(message: FrontendSendMessage):
    logger.info(f"\n\nMessage received:\n{message.uuid}: {message.text}")

    if memory_service.is_reset_request(message.text):
        reply_text = memory_service.reset_session(message.uuid)
        return {"response": reply_text}

    memory_service.add_message(message.uuid, Message(sender=Sender.USER, text=message.text))

    conversation_history = memory_service.get_history(message.uuid)

    start_time = time.time()

    reply = master_router_agent(
        settings=settings,
        db_conn_str=db_conn_str,
        conversation=conversation_history,
        thread_id=message.uuid
    )

    elapsed_time = time.time() - start_time
    logger.info(f"Bot response execution took {elapsed_time:.2f} seconds")

    if isinstance(reply, dict):
        reply_text = reply.get("summary") or reply.get("message") or json.dumps(reply)
    else:
        reply_text = str(reply)

    if "Memory has been reset successfully" in reply_text:
        memory_service.reset_session(message.uuid)
    else:
        memory_service.add_message(message.uuid, Message(sender=Sender.ASSISTANT, text=reply_text))

    logger.info(f"Response sent:\n{reply_text}")

    memory_service.save_history_to_disk(message.uuid)

    return {"response": reply_text}

@router.post("/upload_audio")
async def upload_audio(audio_file: UploadFile = File(...), uuid: str = Form(...)):
    try:
        logger.info(f"\n\nAudio Message received from: {uuid}")

        temp_audio_path = settings.get("TEMP_INCOMING_AUDIO_PATH", "temp_audio")
        if not os.path.exists(temp_audio_path):
            os.makedirs(temp_audio_path)

        history = memory_service.get_history(uuid)

        file_number = len(history.messages_list) + 1
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