"""Fast API class."""
import json
import os
from typing import Dict, List

from fastapi import FastAPI, Request, Response, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
# from faster_whisper import WhisperModel
import logging

from fastapi import WebSocket

from data_models import FrontendSendMessage, MessagesList, Message, Sender, UUIDRequest
from sql_chat_agent import initialize_client_sql_queries_vector_database, sql_agent
from speech_to_text import initialize_speech_to_text_local_whisper_model, \
    speech_to_text_using_local_whisper, speech_to_text_using_openai_whisper, speech_to_text_using_groq_whisper
from text_to_speech import text_to_speech_using_gtts, text_to_speech_using_openai
from utils import get_settings, get_logger

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with specific allowed origins if needed
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

settings = get_settings()
logger = get_logger(settings)
messages_history: Dict[str, MessagesList] = {}

initialize_client_sql_queries_vector_database(settings, logger)


# initialize_speech_to_text_local_whisper_model(logger)
# initialize_text_to_speech_parler_model(logger)


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

    messages_history[message.uuid].add_message(Message(sender=Sender.USER, text=message.text))

    # reply = message.text + " (processed)"  # temp reply
    reply = sql_agent(settings, logger, messages_history[message.uuid])

    messages_history[message.uuid].add_message(Message(sender=Sender.ASSISTANT, text=reply))

    logger.info(f"Response sent:\n{reply}")

    save_chat_history(message.uuid)

    return {"response": reply}


@app.post("/send_audio")
async def send_audio(audio_file: UploadFile = File(...), uuid: str = Form(...)):
    """
    Handles incoming audio messages, converts the audio to text, generates a response,
    and sends the response back to the user along with an audio version of the response.

    Args:
        audio_file (UploadFile): The uploaded audio file sent by the user.
        uuid (str): The UUID associated with the chat session.

    Returns:
        JSONResponse: A JSON response containing the transcribed input audio text, the AI's response text,
        and a URL to access the AI's audio response.

    Raises:
        Exception: If there is an error in processing the audio file or generating the response.
    """
    try:
        logger.info(f"\n\nAudio Message received:\n{uuid}")
        input_audio_file_path = os.path.join(settings.get("TEMP_INCOMING_AUDIO_PATH"),
                                             f"{uuid}_input_{len(messages_history[uuid].messages_list) + 1}.wav")  # wav/webm
        # Save the uploaded audio file temporarily
        with open(input_audio_file_path, "wb") as f:
            f.write(await audio_file.read())

        # Transcribe the audio
        # input_audio_text = "Temp audio extracted text"
        # input_audio_text = speech_to_text_using_local_whisper(logger, input_audio_file_path)
        # input_audio_text = speech_to_text_using_openai_whisper(settings, logger, input_audio_file_path)
        input_audio_text = speech_to_text_using_groq_whisper(settings, logger, input_audio_file_path)
        logger.info(f"Audio converted to text.")

        messages_history[uuid].add_message(Message(sender=Sender.USER, text=input_audio_text))

        # reply = input_audio_text + " (processed)"  # temp reply
        reply = sql_agent(settings, logger, messages_history[uuid])
        logger.info(f"Response generated.")

        messages_history[uuid].add_message(Message(sender=Sender.ASSISTANT, text=reply))

        # output_audio_file_name = f"{uuid}_output_{len(messages_history[uuid].messages_list)}.wav"
        # # output_audio_file_name = "parler_tts_out.wav"  # temp reply
        # output_audio_file_path = os.path.join(settings.get("TEMP_OUTGOING_AUDIO_PATH"), output_audio_file_name)
        # # text_to_speech_using_parler(logger, reply, output_audio_file_path)
        # # text_to_speech_using_gtts(logger, reply, output_audio_file_path)
        # text_to_speech_using_openai(logger, reply, output_audio_file_path)
        #
        # logger.info(f"Response text converted to audio.")
        #
        # # Return the response along with the audio URL
        # audio_url = f"{settings.get('SERVER_FILES_IP')}/get_audio/{output_audio_file_name}"  # Full URL to access audio

        save_chat_history(uuid)

        return JSONResponse(content={
            "input_audio_text": input_audio_text,
            "output_audio_text": reply,
            # "audio_url": audio_url,
        }
        )
    except Exception as e:
        logger.warning(f"Error processing audio: {e}")
        return Response(content="Error processing audio", status_code=500)
    # finally:
    ##     Clean up: remove the temporary file if it exists
    # if os.path.exists(input_audio_file_path):
    #     os.remove(input_audio_file_path)


#
@app.get("/get_audio/{audio_file_name}")
def get_audio(audio_file_name: str):
    """
    Handles requests to retrieve an audio file by its filename.

    Args:
        audio_file_name (str): The name of the audio file to retrieve.

    Returns:
        FileResponse: The requested audio file if it exists.
        Response: An error response with status code 404 if the file is not found.

    """
    logger.info(f"Received request for audio: {audio_file_name}")  # Debug line

    # Construct the full path to the audio file
    file_path = os.path.join(settings.get("TEMP_OUTGOING_AUDIO_PATH"),
                             audio_file_name)  # Safer way to construct file paths

    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="audio/wav", filename="response.wav")
    return Response(content="Audio file not found.", status_code=404)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.get("SERVER_IP"), port=settings.get("SERVER_PORT"))
