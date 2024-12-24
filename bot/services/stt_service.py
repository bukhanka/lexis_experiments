import os
import logging
from typing import Optional

import openai

class STTService:
    """Service for handling Speech-to-Text operations"""
    
    def __init__(self):
        self.client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    def transcribe_voice(self, voice_file_path: str) -> Optional[str]:
        """Transcribe voice message using Whisper API"""
        try:
            with open(voice_file_path, "rb") as audio_file:
                transcription = self.client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file
                )
            return transcription.text
        except Exception as e:
            logging.error(f"Voice transcription error: {e}")
            return None 