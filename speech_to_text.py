"""Contains different methods for speech to text conversion."""
import logging
import os

from dynaconf import Dynaconf
from groq import Groq
from openai import OpenAI

import faster_whisper.transcribe
from faster_whisper import WhisperModel

model: faster_whisper.transcribe.WhisperModel = None


def initialize_speech_to_text_local_whisper_model(logger: logging.getLogger, ):
    """Loading speech to text model from disk."""
    global model
    logger.info("Loading speech to text model...")
    # Load the model with CPU support
    model = WhisperModel("small", device="cpu")  # small, tiny.en


def speech_to_text_using_local_whisper(logger: logging.getLogger, audio_path) -> str:
    """Convert speech to text using local whisper model."""
    try:
        global model
        segments, info = model.transcribe(audio_path)
        return " ".join(segment.text for segment in segments)
    except Exception as e:
        logger.warning(f"Error converting speech to text using local whisper: {e}")
        return f"Error converting speech to text using local whisper: {e}"


def speech_to_text_using_openai_whisper(settings: Dynaconf, logger: logging.getLogger, audio_path) -> str:
    """Convert speech to text using openai whisper model."""
    try:
        os.environ["OPENAI_API_KEY"] = settings.get("OPENAI_API_KEY")
        client = OpenAI()

        audio_file = open(audio_path, "rb")
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file
        )
        return transcription.text
    except Exception as e:
        logger.warning(f"Error converting speech to text using openai whisper: {e}")
        return f"Error converting speech to text using openai whisper: {e}"


def speech_to_text_using_groq_whisper(settings: Dynaconf, logger: logging.getLogger, audio_path) -> str:
    """Convert speech to text using groq whisper model."""
    try:
        os.environ["GROQ_API_KEY"] = settings.get("GROQ_API_KEY")

        # Initialize the Groq client
        client = Groq()
        # Open the audio file
        with open(audio_path, "rb") as file:
            # Create a transcription of the audio file
            transcription = client.audio.transcriptions.create(
                file=(audio_path, file.read()),  # Required audio file
                # distil-whisper-large-v3-en, whisper-large-v3
                model="whisper-large-v3",  # Required model to use for transcription
                # prompt="Specify context or spelling",  # Optional
                response_format="json",  # Optional
                language="en",  # Optional
                temperature=0.0  # Optional
            )
            # Print the transcription text
            return transcription.text
    except Exception as e:
        logger.warning(f"Error converting speech to text using groq whisper: {e}")
        return f"Error converting speech to text using groq whisper: {e}"




