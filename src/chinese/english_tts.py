"""
English TTS adapter module.

Provides an async generator interface for English text-to-speech that reuses
the kokoro_english instance from src/other/main.py.

This module adapts the English Kokoro model to produce PCM output compatible
with the Chinese TTS output format (same sample rate, bit depth, channels).
"""

import sys
import os
import pathlib
import logging
from typing import Optional, AsyncGenerator, Tuple, Any

import numpy as np

# Ensure src is on sys.path for importing other modules
SRC_DIR = str(pathlib.Path(__file__).resolve().parents[1])
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

logger = logging.getLogger(__name__)

# Default English voice (from v1.0 model)
DEFAULT_ENGLISH_VOICE = "af_heart"

# Lazily loaded references to the English model components
_kokoro_english: Optional[Any] = None
_g2p_english: Optional[Any] = None
_english_model_loaded = False


def _ensure_english_model_loaded() -> bool:
    """
    Ensure the English Kokoro model and G2P converter are loaded.
    
    Returns True if models are available, False otherwise.
    
    This lazily loads the models from src/other/main module on first call.
    """
    global _kokoro_english, _g2p_english, _english_model_loaded
    
    if _english_model_loaded:
        return _kokoro_english is not None and _g2p_english is not None
    
    _english_model_loaded = True  # Mark as attempted even if it fails
    
    try:
        # Try to import from src.other.main
        from other.main import kokoro_model as english_model, g2p_converter as english_g2p
        
        if english_model is not None and english_g2p is not None:
            _kokoro_english = english_model
            _g2p_english = english_g2p
            logger.info("English Kokoro model loaded successfully from other.main")
            return True
        else:
            logger.warning("English Kokoro model not initialized in other.main")
            return False
    except ImportError as e:
        logger.warning(f"Could not import English model from other.main: {e}")
        return False
    except Exception as e:
        logger.exception(f"Error loading English model: {e}")
        return False


async def create_english_stream(
    text: str,
    voice: Optional[str] = None,
    speed: float = 1.0,
    sample_rate: int = 24000
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Create an async generator that yields audio chunks for English text.
    
    This function adapts the English Kokoro model's create_stream method
    to provide a consistent interface with the Chinese TTS.
    
    Args:
        text: English text to synthesize
        voice: Voice name (default: "af_heart" for English v1.0 model)
        speed: Speech speed multiplier (default: 1.0)
        sample_rate: Target sample rate (default: 24000, which matches Kokoro output)
    
    Yields:
        Tuple of (audio_samples as numpy array, sample_rate)
        
    Raises:
        RuntimeError: If English model is not available
    """
    if not text or not text.strip():
        return
    
    if not _ensure_english_model_loaded():
        logger.error("English TTS model not available")
        raise RuntimeError("English TTS model not available. Please ensure src/other/main.py startup has run.")
    
    voice = voice or DEFAULT_ENGLISH_VOICE
    
    try:
        # Convert text to phonemes using English G2P
        phonemes, _ = _g2p_english(text)
        logger.debug(f"English G2P: '{text[:50]}...' -> phonemes generated")
    except Exception as e:
        logger.exception(f"English G2P conversion failed for text: {text[:100]}")
        raise RuntimeError(f"English G2P conversion failed: {e}")
    
    try:
        # Check if create_stream is available (streaming mode)
        if hasattr(_kokoro_english, 'create_stream'):
            # Use streaming mode - yields chunks progressively
            stream = _kokoro_english.create_stream(
                phonemes,
                voice=voice,
                speed=speed,
                is_phonemes=True
            )
            
            # Yield chunks from the stream
            async for audio_chunk, sr in stream:
                # Ensure consistent sample rate if needed
                if sr != sample_rate and sample_rate != 24000:
                    audio_chunk = _resample_audio(audio_chunk, sr, sample_rate)
                    sr = sample_rate
                yield (audio_chunk, sr)
        else:
            # Fallback to non-streaming create method
            samples, sr = _kokoro_english.create(
                phonemes,
                voice=voice,
                speed=speed,
                is_phonemes=True
            )
            
            # Ensure consistent sample rate if needed
            if sr != sample_rate and sample_rate != 24000:
                samples = _resample_audio(samples, sr, sample_rate)
                sr = sample_rate
            
            yield (samples, sr)
            
    except Exception as e:
        logger.exception(f"English TTS synthesis failed for text: {text[:100]}")
        raise RuntimeError(f"English TTS synthesis failed: {e}")


def _resample_audio(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """
    Simple linear interpolation resampling.
    
    For production use, consider using scipy.signal.resample or librosa.
    """
    if orig_sr == target_sr:
        return samples
    
    samples = np.asarray(samples, dtype=np.float32)
    duration = samples.shape[0] / float(orig_sr)
    new_len = max(1, int(round(duration * target_sr)))
    
    if new_len == samples.shape[0]:
        return samples
    
    old_idx = np.linspace(0, samples.shape[0] - 1, samples.shape[0])
    new_idx = np.linspace(0, samples.shape[0] - 1, new_len)
    result = np.interp(new_idx, old_idx, samples).astype(np.float32)
    
    return result


def set_english_model(kokoro_model: Any, g2p_converter: Any) -> None:
    """
    Manually set the English model and G2P converter.
    
    This is useful for:
    1. Testing with mock models
    2. Explicit initialization without relying on lazy loading
    3. Using a different model instance than the one in other.main
    
    Args:
        kokoro_model: The Kokoro model instance for English TTS
        g2p_converter: The G2P converter for English text
    """
    global _kokoro_english, _g2p_english, _english_model_loaded
    
    _kokoro_english = kokoro_model
    _g2p_english = g2p_converter
    _english_model_loaded = True
    
    logger.info("English model manually set")


def is_english_model_available() -> bool:
    """
    Check if English TTS model is available for use.
    """
    return _ensure_english_model_loaded()
