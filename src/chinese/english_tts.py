"""
English TTS adapter for the Chinese module.

This module provides an adapter to use the English TTS model (from src/other)
within the Chinese module, enabling mixed Chinese-English text synthesis.

The adapter wraps the English model loading and synthesis logic, providing
an interface compatible with the Chinese kokoro_model.create_stream.
"""

import os
import pathlib
import logging
import importlib.util
from typing import Optional, AsyncGenerator, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Path to src/other for model files
CURRENT_DIR = pathlib.Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
OTHER_DIR = SRC_DIR / "other"
OTHER_MODELS_DIR = OTHER_DIR / "models"

# Global instances for English model and G2P converter
_english_kokoro_model = None
_english_g2p_converter = None
_english_model_lock = None  # Will be initialized on first use
_download_deps_module = None


def _load_download_deps_module():
    """
    Safely load the download_deps module from src/other using importlib.
    This avoids modifying sys.path which can cause side effects.
    
    Returns:
        The download_deps module or None if loading fails.
    """
    global _download_deps_module
    if _download_deps_module is not None:
        return _download_deps_module
    
    try:
        module_path = OTHER_DIR / "download_deps.py"
        if not module_path.exists():
            logger.error(f"download_deps.py not found at {module_path}")
            return None
        
        spec = importlib.util.spec_from_file_location("other_download_deps", module_path)
        if spec is None or spec.loader is None:
            logger.error(f"Failed to create module spec for {module_path}")
            return None
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _download_deps_module = module
        return module
    except Exception as e:
        logger.exception(f"Failed to load download_deps module: {e}")
        return None


def _ensure_dependencies_downloaded() -> bool:
    """
    Ensure English model dependencies are downloaded.
    Uses the download_deps module from src/other.
    
    Returns:
        True if dependencies are ready, False otherwise.
    """
    try:
        download_deps = _load_download_deps_module()
        if download_deps is None:
            logger.error("Could not load download_deps module")
            return False
        
        download_deps.ensure_dir_exists(str(OTHER_MODELS_DIR))
        return download_deps.check_and_download_dependencies()
    except Exception as e:
        logger.exception(f"Failed to download English model dependencies: {e}")
        return False


def get_english_model():
    """
    Get or initialize the English Kokoro model instance.
    
    Returns:
        Tuple of (kokoro_model, g2p_converter) or (None, None) if loading fails.
    """
    global _english_kokoro_model, _english_g2p_converter
    
    if _english_kokoro_model is not None and _english_g2p_converter is not None:
        return _english_kokoro_model, _english_g2p_converter
    
    try:
        # Ensure dependencies are downloaded
        if not _ensure_dependencies_downloaded():
            logger.error("English model dependencies not available")
            return None, None
        
        # Check if model files exist
        model_path = OTHER_MODELS_DIR / "kokoro-v1.0.onnx"
        voices_path = OTHER_MODELS_DIR / "voices-v1.0.bin"
        
        if not model_path.exists() or not voices_path.exists():
            logger.error(f"English model files not found in {OTHER_MODELS_DIR}")
            return None, None
        
        # Import required modules
        from kokoro_onnx import Kokoro
        from misaki import en, espeak
        
        # Load model
        logger.info(f"Loading English Kokoro model from {model_path}")
        _english_kokoro_model = Kokoro(str(model_path), str(voices_path))
        
        # Initialize English G2P with espeak fallback
        fallback = espeak.EspeakFallback(british=False)
        _english_g2p_converter = en.G2P(trf=False, british=False, fallback=fallback)
        
        logger.info("English Kokoro model and G2P converter loaded successfully")
        return _english_kokoro_model, _english_g2p_converter
        
    except Exception as e:
        logger.exception(f"Failed to load English model: {e}")
        return None, None


def convert_english_text_to_phonemes(text: str) -> Optional[str]:
    """
    Convert English text to phonemes using the English G2P converter.
    
    Args:
        text: English text to convert.
        
    Returns:
        Phonemes string or None if conversion fails.
    """
    model, g2p = get_english_model()
    if g2p is None:
        logger.error("English G2P converter not available")
        return None
    
    try:
        phonemes, _ = g2p(text)
        return phonemes
    except Exception as e:
        logger.exception(f"English G2P conversion failed: {e}")
        return None


def create_english_audio(text: str, voice: str = "af_heart", speed: float = 1.0) -> Optional[Tuple[np.ndarray, int]]:
    """
    Create audio from English text (non-streaming).
    
    Args:
        text: English text to synthesize.
        voice: Voice name to use (default: af_heart).
        speed: Speech speed multiplier (default: 1.0).
        
    Returns:
        Tuple of (samples, sample_rate) or None if synthesis fails.
    """
    model, g2p = get_english_model()
    if model is None or g2p is None:
        logger.error("English model not available")
        return None
    
    try:
        phonemes, _ = g2p(text)
        samples, sample_rate = model.create(phonemes, voice=voice, speed=speed, is_phonemes=True)
        return samples, sample_rate
    except Exception as e:
        logger.exception(f"English audio synthesis failed: {e}")
        return None


async def create_english_stream(
    text: str,
    voice: str = "af_heart",
    speed: float = 1.0
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Create an async generator stream from English text.
    
    This function provides an interface compatible with the Chinese
    kokoro_model.create_stream by converting the English model's output
    to an async generator.
    
    The English model uses kokoro_onnx which provides create_stream method
    that yields (samples, sample_rate) tuples.
    
    Args:
        text: English text to synthesize.
        voice: Voice name to use (default: af_heart).
        speed: Speech speed multiplier (default: 1.0).
        
    Yields:
        Tuples of (audio_samples, sample_rate) as the audio is generated.
    """
    model, g2p = get_english_model()
    if model is None or g2p is None:
        logger.error("English model not available for streaming")
        return
    
    try:
        phonemes, _ = g2p(text)
        
        # Check if create_stream exists on the model
        if hasattr(model, 'create_stream'):
            # Use the streaming interface
            stream = model.create_stream(phonemes, voice=voice, speed=speed, is_phonemes=True)
            
            # Handle both sync and async generators
            if hasattr(stream, '__anext__'):
                # Async generator
                async for chunk in stream:
                    yield chunk
            else:
                # Sync generator - wrap in async
                for chunk in stream:
                    yield chunk
        else:
            # Fallback to non-streaming create and yield as single chunk
            logger.warning("English model doesn't support create_stream, using create as fallback")
            samples, sample_rate = model.create(phonemes, voice=voice, speed=speed, is_phonemes=True)
            yield (samples, sample_rate)
            
    except Exception as e:
        logger.exception(f"English stream creation failed: {e}")
        return


def create_english_stream_sync(
    text: str,
    voice: str = "af_heart", 
    speed: float = 1.0
):
    """
    Create a sync generator stream from English text.
    
    This is a synchronous version that can be used when async is not needed.
    
    Args:
        text: English text to synthesize.
        voice: Voice name to use (default: af_heart).
        speed: Speech speed multiplier (default: 1.0).
        
    Yields:
        Tuples of (audio_samples, sample_rate) as the audio is generated.
    """
    model, g2p = get_english_model()
    if model is None or g2p is None:
        logger.error("English model not available for streaming")
        return
    
    try:
        phonemes, _ = g2p(text)
        
        # Check if create_stream exists on the model
        if hasattr(model, 'create_stream'):
            # Use the streaming interface
            stream = model.create_stream(phonemes, voice=voice, speed=speed, is_phonemes=True)
            yield from stream
        else:
            # Fallback to non-streaming create and yield as single chunk
            logger.warning("English model doesn't support create_stream, using create as fallback")
            samples, sample_rate = model.create(phonemes, voice=voice, speed=speed, is_phonemes=True)
            yield (samples, sample_rate)
            
    except Exception as e:
        logger.exception(f"English stream creation failed: {e}")
        return


# Export public API
__all__ = [
    'get_english_model',
    'convert_english_text_to_phonemes',
    'create_english_audio',
    'create_english_stream',
    'create_english_stream_sync',
]
