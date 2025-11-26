"""
English TTS adapter for the Chinese service.

This module provides an adapter to use English TTS (from src/other) within the
Chinese service, ensuring output format compatibility with the Chinese TTS.

The adapter wraps the English Kokoro model and provides a create_stream interface
that is compatible with the Chinese kokoro_model.create_stream.
"""

import os
import sys
import logging
from typing import Optional, AsyncGenerator, Tuple
import numpy as np

# Ensure src is on sys.path before importing local modules
import pathlib
SRC_DIR = str(pathlib.Path(__file__).resolve().parents[1])
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

logger = logging.getLogger(__name__)

# Global variables for English model and G2P converter
_english_kokoro_model = None
_english_g2p_converter = None
_english_model_initialized = False

# Model paths relative to this file's directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")

# English model files (v1.0)
ENGLISH_MODEL_FILENAME = "kokoro-v1.0.onnx"
ENGLISH_VOICES_FILENAME = "voices-v1.0.bin"

# Download URLs for English model
ENGLISH_DEPENDENCIES = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
}


def ensure_english_model_files() -> bool:
    """
    Check and download English model files if they don't exist.
    
    Returns:
        True if all files are present (downloaded or already existed), False otherwise.
    """
    import requests
    
    if not os.path.exists(MODELS_DIR):
        os.makedirs(MODELS_DIR)
    
    all_present = True
    for filename, url in ENGLISH_DEPENDENCIES.items():
        local_path = os.path.join(MODELS_DIR, filename)
        if not os.path.exists(local_path):
            logger.info(f"Downloading English model file: {filename}")
            try:
                with requests.get(url, stream=True) as r:
                    r.raise_for_status()
                    with open(local_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                logger.info(f"Downloaded: {filename}")
            except Exception as e:
                logger.error(f"Failed to download {filename}: {e}")
                if os.path.exists(local_path):
                    os.remove(local_path)
                all_present = False
    
    return all_present


def initialize_english_model() -> bool:
    """
    Initialize the English Kokoro model and G2P converter.
    
    This should be called once during application startup.
    
    Returns:
        True if initialization was successful, False otherwise.
    """
    global _english_kokoro_model, _english_g2p_converter, _english_model_initialized
    
    if _english_model_initialized:
        return _english_kokoro_model is not None
    
    try:
        # Ensure model files exist
        if not ensure_english_model_files():
            logger.error("English model files not available")
            _english_model_initialized = True
            return False
        
        model_path = os.path.join(MODELS_DIR, ENGLISH_MODEL_FILENAME)
        voices_path = os.path.join(MODELS_DIR, ENGLISH_VOICES_FILENAME)
        
        if not (os.path.exists(model_path) and os.path.exists(voices_path)):
            logger.error(f"English model files missing in {MODELS_DIR}")
            _english_model_initialized = True
            return False
        
        # Import and initialize model
        from kokoro_onnx import Kokoro
        from misaki import en, espeak
        
        _english_kokoro_model = Kokoro(model_path, voices_path)
        
        # English G2P with espeak-ng fallback
        fallback = espeak.EspeakFallback(british=False)
        _english_g2p_converter = en.G2P(trf=False, british=False, fallback=fallback)
        
        logger.info("English Kokoro model and G2P converter initialized successfully")
        _english_model_initialized = True
        return True
        
    except Exception as e:
        logger.exception(f"Failed to initialize English model: {e}")
        _english_model_initialized = True
        return False


def is_english_model_ready() -> bool:
    """Check if the English model is initialized and ready."""
    return _english_kokoro_model is not None and _english_g2p_converter is not None


def get_english_phonemes(text: str) -> str:
    """
    Convert English text to phonemes using the English G2P converter.
    
    Args:
        text: English text to convert.
    
    Returns:
        Phoneme string for the input text.
    
    Raises:
        RuntimeError: If English model is not initialized.
    """
    if not is_english_model_ready():
        raise RuntimeError("English model not initialized. Call initialize_english_model() first.")
    
    phonemes, _ = _english_g2p_converter(text)
    return phonemes


async def create_english_stream(
    text: str,
    voice: str = "af_heart",
    speed: float = 1.0
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Create an async generator for English TTS streaming.
    
    This function provides a compatible interface with kokoro_model.create_stream
    for English text synthesis.
    
    Args:
        text: English text to synthesize.
        voice: Voice model to use (default: af_heart for English v1.0).
        speed: Speech speed multiplier.
    
    Yields:
        Tuples of (audio_samples, sample_rate) where audio_samples is a numpy array
        of float32 samples and sample_rate is the sampling rate (typically 24000).
    
    Raises:
        RuntimeError: If English model is not initialized.
    """
    if not is_english_model_ready():
        raise RuntimeError("English model not initialized. Call initialize_english_model() first.")
    
    try:
        # Convert text to phonemes
        phonemes = get_english_phonemes(text)
        
        # Use the English model's create_stream
        stream_gen = _english_kokoro_model.create_stream(
            phonemes,
            voice=voice,
            speed=speed,
            is_phonemes=True
        )
        
        # Yield audio chunks from the stream
        async for audio_chunk, sample_rate in stream_gen:
            yield audio_chunk, sample_rate
            
    except Exception as e:
        logger.exception(f"Error in English TTS streaming: {e}")
        raise


def create_english_audio(
    text: str,
    voice: str = "af_heart",
    speed: float = 1.0
) -> Tuple[np.ndarray, int]:
    """
    Create audio for English text (non-streaming version).
    
    Args:
        text: English text to synthesize.
        voice: Voice model to use.
        speed: Speech speed multiplier.
    
    Returns:
        Tuple of (audio_samples, sample_rate).
    
    Raises:
        RuntimeError: If English model is not initialized.
    """
    if not is_english_model_ready():
        raise RuntimeError("English model not initialized. Call initialize_english_model() first.")
    
    phonemes = get_english_phonemes(text)
    samples, sample_rate = _english_kokoro_model.create(
        phonemes,
        voice=voice,
        speed=speed,
        is_phonemes=True
    )
    return samples, sample_rate


# Default English voice mapping (can be extended)
DEFAULT_ENGLISH_VOICE = "af_heart"

def get_default_english_voice() -> str:
    """Get the default English voice."""
    return DEFAULT_ENGLISH_VOICE
