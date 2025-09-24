"""Contains different methods for text to speech conversion."""
import torch
import transformers
from openai import OpenAI
# from gtts import gTTS
# import parler_tts
# from parler_tts import ParlerTTSForConditionalGeneration
# from transformers import AutoTokenizer
# import soundfile as sf

import logging



def text_to_speech_using_gtts(logger: logging.getLogger, text: str, audio_path: str):
    """Convert text to speech using Google Text to Speech (gTTS) model."""
    try:
        # Use gTTS to generate speech audio
        tts = gTTS(text, lang='en')
        # Save the generated MP3 to the output path
        tts.save(audio_path)

    except Exception as e:
        logger.warning(f"Error converting text to speech using 'gTTS': {e}")
        return f"Error converting text to speech using 'gTTS': {e}"


def text_to_speech_using_openai(logger: logging.getLogger, text: str, audio_path: str):
    """Convert text to speech using openai model."""
    try:
        client = OpenAI()

        response = client.audio.speech.create(
            model="tts-1-hd",  # tts-1 or tts-1-hd
            # https://platform.openai.com/docs/guides/text-to-speech/quickstart
            voice="alloy", # alloy, echo, fable, onyx, nova, and shimmer.
            input=text,
            speed= 1.25,  # 0.25 to 4.0. 1.0
        )

        response.stream_to_file(audio_path)

    except Exception as e:
        logger.warning(f"Error converting text to speech using 'gTTS': {e}")
        return f"Error converting text to speech using 'gTTS': {e}"
