"""
English TTS adapter that reuses the already-initialized English Kokoro instance
from src/other/main.py.
"""
import asyncio
import inspect
import logging
import sys
import os
from typing import AsyncGenerator, Tuple, Optional, Any

import numpy as np

logger = logging.getLogger(__name__)

# Ensure src directory is in path for imports
_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)


def _get_english_tts():
    """
    Get the English Kokoro model and G2P converter.
    
    Returns:
        Tuple of (kokoro_model, g2p_converter) from src.other.main
        
    Raises:
        RuntimeError: If models are not available or not initialized.
    """
    try:
        from other.main import kokoro_model as kokoro_english, g2p_converter as en_g2p
    except ImportError:
        try:
            from src.other.main import kokoro_model as kokoro_english, g2p_converter as en_g2p
        except ImportError:
            logger.error("Failed to import English Kokoro model from src.other.main")
            raise RuntimeError("English Kokoro model not available")
    
    return kokoro_english, en_g2p


async def create_english_stream(
    text: str,
    voice: str = "af_heart",
    speed: float = 1.0,
    sample_rate: int = 24000,
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Create an async generator that yields (audio_samples, sample_rate) tuples
    for the given English text.
    
    This function reuses the already-initialized English Kokoro instance
    (kokoro_model from src.other.main) to avoid reloading the model.
    
    Args:
        text: English text to synthesize.
        voice: Voice name (e.g., 'af_heart').
        speed: Speech speed (default 1.0).
        sample_rate: Target sample rate (default 24000).
        
    Yields:
        Tuples of (audio_samples: np.ndarray, sample_rate: int)
    """
    # Get English TTS instances using helper function
    kokoro_english, en_g2p = _get_english_tts()
    
    if kokoro_english is None:
        logger.error("English Kokoro model (kokoro_model) is not initialized")
        raise RuntimeError("English Kokoro model not initialized. Please ensure the English TTS service has started.")
    
    if en_g2p is None:
        logger.error("English G2P converter is not initialized")
        raise RuntimeError("English G2P converter not initialized. Please ensure the English TTS service has started.")
    
    try:
        # Convert text to phonemes using English G2P
        phonemes, _ = en_g2p(text)
        logger.debug(f"[english_tts] Converted '{text[:50]}...' to phonemes")
        
        # Check if kokoro_english has create_stream method
        if hasattr(kokoro_english, 'create_stream'):
            # Get the stream generator
            stream_gen = kokoro_english.create_stream(
                phonemes, 
                voice=voice, 
                speed=speed, 
                is_phonemes=True
            )
            
            # Handle both async generator and coroutine returning async generator
            if inspect.iscoroutine(stream_gen):
                stream_gen = await stream_gen
            
            # Yield from the stream
            async for audio_chunk, sr in stream_gen:
                yield (audio_chunk, sr)
        else:
            # Fallback to synchronous create() method
            logger.debug("[english_tts] Using synchronous create() method")
            samples, sr = kokoro_english.create(
                phonemes, 
                voice=voice, 
                speed=speed, 
                is_phonemes=True
            )
            yield (samples, sr)
            
    except Exception as e:
        logger.exception(f"[english_tts] Error generating English speech: {e}")
        raise


async def normalize_stream_output(
    async_gen: AsyncGenerator[Tuple[Any, int], None],
    target_sample_rate: int = 24000
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Normalize the output of a TTS stream to ensure consistent format.
    
    - Ensures audio samples are numpy float32 arrays
    - Handles sample rate conversion if needed
    
    Args:
        async_gen: Input async generator yielding (samples, sample_rate) tuples.
        target_sample_rate: Target sample rate for output.
        
    Yields:
        Normalized (audio_samples: np.ndarray, sample_rate: int) tuples.
    """
    async for samples, sr in async_gen:
        # Convert to numpy array if needed
        if not isinstance(samples, np.ndarray):
            samples = np.array(samples, dtype=np.float32)
        
        # Ensure float32
        if samples.dtype != np.float32:
            if np.issubdtype(samples.dtype, np.integer):
                # Assume int16
                samples = samples.astype(np.float32) / 32768.0
            else:
                samples = samples.astype(np.float32)
        
        yield (samples, sr)
