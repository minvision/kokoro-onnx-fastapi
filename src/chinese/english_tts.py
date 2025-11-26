"""
english_tts.py - English TTS Wrapper Module

Provides access to the English Kokoro instance (kokoro_english from src/other/main.py)
for creating English audio streams. Ensures PCM output format is consistent with Chinese TTS.
"""

import os
import sys
import pathlib
import logging
import asyncio
from typing import Optional, AsyncGenerator, Tuple, Any

import numpy as np

logger = logging.getLogger(__name__)

# Global variables for English model and G2P (lazy-loaded)
_english_kokoro: Optional[Any] = None
_english_g2p: Optional[Any] = None
_english_init_lock = asyncio.Lock()
_english_init_done = False

# English model paths (relative to src/other)
OTHER_DIR = pathlib.Path(__file__).resolve().parents[1] / "other"
ENGLISH_MODELS_DIR = OTHER_DIR / "models"


async def _ensure_english_model_loaded() -> bool:
    """
    Ensure the English Kokoro model and G2P converter are loaded.
    Returns True if successfully loaded, False otherwise.
    
    This lazily loads the English model on first use to avoid loading it
    during Chinese-only requests.
    """
    global _english_kokoro, _english_g2p, _english_init_done
    
    if _english_init_done:
        return _english_kokoro is not None and _english_g2p is not None
    
    async with _english_init_lock:
        # Double-check after acquiring lock
        if _english_init_done:
            return _english_kokoro is not None and _english_g2p is not None
        
        try:
            from kokoro_onnx import Kokoro
            from misaki import en, espeak
            
            model_path = ENGLISH_MODELS_DIR / "kokoro-v1.0.onnx"
            voices_path = ENGLISH_MODELS_DIR / "voices-v1.0.bin"
            
            if not model_path.exists() or not voices_path.exists():
                logger.error(f"English model files not found in {ENGLISH_MODELS_DIR}. "
                           f"Please ensure kokoro-v1.0.onnx and voices-v1.0.bin exist.")
                _english_init_done = True
                return False
            
            # Load English Kokoro model
            _english_kokoro = Kokoro(str(model_path), str(voices_path))
            
            # Load English G2P with espeak fallback
            fallback = espeak.EspeakFallback(british=False)
            _english_g2p = en.G2P(trf=False, british=False, fallback=fallback)
            
            logger.info("English Kokoro model and G2P converter loaded successfully.")
            _english_init_done = True
            return True
            
        except Exception as e:
            logger.exception(f"Failed to load English Kokoro model: {e}")
            _english_init_done = True
            return False


def get_english_kokoro():
    """Get the English Kokoro instance (may be None if not loaded)."""
    return _english_kokoro


def get_english_g2p():
    """Get the English G2P converter (may be None if not loaded)."""
    return _english_g2p


async def create_english_stream(
    text: str,
    voice: Optional[str] = None,
    speed: float = 1.0,
    sample_rate: int = 24000
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Create an async generator that yields English audio chunks.
    
    This wraps the English Kokoro model's create_stream method and ensures
    the output format is consistent with the Chinese TTS output.
    
    Args:
        text: English text to synthesize
        voice: Voice name (e.g., 'af_heart'). Defaults to 'af_heart' if not specified.
        speed: Speech speed (default: 1.0)
        sample_rate: Output sample rate (default: 24000)
        
    Yields:
        Tuple of (audio_samples: np.ndarray, sample_rate: int)
        
    Raises:
        RuntimeError: If English model is not available
    """
    # Ensure model is loaded
    loaded = await _ensure_english_model_loaded()
    if not loaded or _english_kokoro is None or _english_g2p is None:
        raise RuntimeError("English TTS model is not available. "
                          "Please ensure the model files exist in src/other/models/")
    
    # Default voice for English
    if voice is None:
        voice = "af_heart"
    
    # Convert text to phonemes using English G2P
    try:
        phonemes, _ = _english_g2p(text)
    except Exception as e:
        logger.exception(f"English G2P conversion failed for text: {text[:100]}...")
        raise RuntimeError(f"English G2P conversion failed: {e}")
    
    # Create stream from the English model
    try:
        stream_result = _english_kokoro.create_stream(
            phonemes, 
            voice=voice, 
            speed=speed, 
            is_phonemes=True
        )
        
        # Handle both coroutine and async generator cases
        if asyncio.iscoroutine(stream_result):
            stream_result = await stream_result
        
        # If it's an async generator, iterate over it
        if hasattr(stream_result, '__anext__'):
            async for audio_chunk, sr in stream_result:
                yield (np.asarray(audio_chunk, dtype=np.float32), int(sr))
        elif hasattr(stream_result, '__next__'):
            # Sync generator - wrap in async
            for audio_chunk, sr in stream_result:
                yield (np.asarray(audio_chunk, dtype=np.float32), int(sr))
                await asyncio.sleep(0)  # Yield control
        else:
            # Single result (samples, sr)
            samples, sr = stream_result
            yield (np.asarray(samples, dtype=np.float32), int(sr))
            
    except Exception as e:
        logger.exception(f"English TTS stream creation failed: {e}")
        raise RuntimeError(f"English TTS stream creation failed: {e}")
