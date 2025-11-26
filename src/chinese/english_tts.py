"""
English TTS module.
Provides English text-to-speech functionality using Kokoro v1.0 model.
Can be used standalone or integrated with mixed TTS for Chinese-English mixed text.
"""

import os
import logging
from typing import Optional, Tuple, AsyncIterator
import numpy as np

logger = logging.getLogger(__name__)

# Module-level model instances (lazy loaded)
_english_model = None
_english_g2p = None
_model_loaded = False

# Model paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")

# English model file names
ENGLISH_MODEL_FILE = "kokoro-v1.0.onnx"
ENGLISH_VOICES_FILE = "voices-v1.0.bin"


def get_english_model_paths() -> Tuple[str, str]:
    """Get paths to English model files."""
    model_path = os.path.join(MODELS_DIR, ENGLISH_MODEL_FILE)
    voices_path = os.path.join(MODELS_DIR, ENGLISH_VOICES_FILE)
    return model_path, voices_path


def check_english_model_exists() -> bool:
    """Check if English model files exist."""
    model_path, voices_path = get_english_model_paths()
    return os.path.exists(model_path) and os.path.exists(voices_path)


def load_english_model() -> bool:
    """
    Load the English TTS model and G2P converter.
    
    Returns:
        True if loaded successfully, False otherwise
    """
    global _english_model, _english_g2p, _model_loaded
    
    if _model_loaded:
        return True
    
    model_path, voices_path = get_english_model_paths()
    
    if not os.path.exists(model_path):
        logger.warning(f"English model file not found: {model_path}")
        return False
    
    if not os.path.exists(voices_path):
        logger.warning(f"English voices file not found: {voices_path}")
        return False
    
    try:
        from kokoro_onnx import Kokoro
        from misaki import en, espeak
        
        # Load model
        _english_model = Kokoro(model_path, voices_path)
        
        # Load English G2P with espeak fallback
        try:
            fallback = espeak.EspeakFallback(british=False)
            _english_g2p = en.G2P(trf=False, british=False, fallback=fallback)
        except Exception as e:
            # Try without espeak fallback if not available
            logger.warning(f"espeak fallback not available: {e}, trying without")
            _english_g2p = en.G2P(trf=False, british=False)
        
        _model_loaded = True
        logger.info("English TTS model and G2P loaded successfully")
        return True
        
    except Exception as e:
        logger.exception(f"Failed to load English TTS model: {e}")
        return False


def unload_english_model():
    """Unload the English model to free memory."""
    global _english_model, _english_g2p, _model_loaded
    _english_model = None
    _english_g2p = None
    _model_loaded = False
    logger.info("English TTS model unloaded")


def is_english_model_loaded() -> bool:
    """Check if English model is currently loaded."""
    return _model_loaded


def synthesize_english(
    text: str,
    voice: str = "af_heart",
    speed: float = 1.0
) -> Optional[Tuple[np.ndarray, int]]:
    """
    Synthesize English text to audio.
    
    Args:
        text: English text to synthesize
        voice: Voice model name (e.g., 'af_heart')
        speed: Speech speed (1.0 = normal)
        
    Returns:
        Tuple of (audio_samples, sample_rate) or None if failed
    """
    global _english_model, _english_g2p
    
    if not _model_loaded:
        if not load_english_model():
            logger.error("English model not available")
            return None
    
    try:
        # Convert text to phonemes
        phonemes, _ = _english_g2p(text)
        
        # Synthesize audio
        samples, sample_rate = _english_model.create(
            phonemes,
            voice=voice,
            speed=speed,
            is_phonemes=True
        )
        
        return samples, sample_rate
        
    except Exception as e:
        logger.exception(f"English TTS synthesis failed: {e}")
        return None


def create_english_stream(
    text: str,
    voice: str = "af_heart",
    speed: float = 1.0
) -> Optional[AsyncIterator[Tuple[np.ndarray, int]]]:
    """
    Create a streaming generator for English TTS.
    
    Args:
        text: English text to synthesize
        voice: Voice model name
        speed: Speech speed
        
    Returns:
        Async iterator yielding (audio_chunk, sample_rate) tuples
    """
    global _english_model, _english_g2p
    
    if not _model_loaded:
        if not load_english_model():
            logger.error("English model not available")
            return None
    
    try:
        # Convert text to phonemes
        phonemes, _ = _english_g2p(text)
        
        # Create streaming generator
        stream = _english_model.create_stream(
            phonemes,
            voice=voice,
            speed=speed,
            is_phonemes=True
        )
        
        return stream
        
    except Exception as e:
        logger.exception(f"Failed to create English TTS stream: {e}")
        return None


def get_english_phonemes(text: str) -> Optional[str]:
    """
    Convert English text to phonemes without synthesis.
    
    Args:
        text: English text
        
    Returns:
        Phonemes string or None if conversion failed
    """
    global _english_g2p
    
    if not _model_loaded:
        if not load_english_model():
            return None
    
    try:
        phonemes, _ = _english_g2p(text)
        return phonemes
    except Exception as e:
        logger.exception(f"English G2P conversion failed: {e}")
        return None


# Default English voice options (from v1.0 model)
ENGLISH_VOICES = [
    "af_heart",      # American Female - Heart
    "af_nicole",     # American Female - Nicole
    "af_sky",        # American Female - Sky
    "af_bella",      # American Female - Bella
    "af_sarah",      # American Female - Sarah
    "am_adam",       # American Male - Adam
    "am_michael",    # American Male - Michael
    "bf_emma",       # British Female - Emma
    "bf_isabella",   # British Female - Isabella
    "bm_george",     # British Male - George
    "bm_lewis",      # British Male - Lewis
]


def get_default_english_voice() -> str:
    """Get default English voice."""
    return "af_heart"


def is_valid_english_voice(voice: str) -> bool:
    """Check if voice is a valid English voice name."""
    # Allow any voice name that follows pattern: [ab][fm]_*
    if len(voice) < 4:
        return False
    return voice[0] in 'ab' and voice[1] in 'fm' and voice[2] == '_'
