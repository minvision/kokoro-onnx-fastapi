"""
Mixed language (Chinese/English) TTS stream module.

Provides a unified async generator interface for synthesizing mixed Chinese/English text
by segmenting the input and routing each segment to the appropriate TTS model.
"""

import sys
import pathlib
import logging
from typing import Optional, AsyncGenerator, Tuple, Any

import numpy as np

# Ensure src is on sys.path
SRC_DIR = str(pathlib.Path(__file__).resolve().parents[1])
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from chinese.lang_split import split_text_into_segments
from chinese.english_tts import create_english_stream, is_english_model_available

logger = logging.getLogger(__name__)

# Default voices
DEFAULT_CHINESE_VOICE = "zf_001"
DEFAULT_ENGLISH_VOICE = "af_heart"


async def create_mixed_stream(
    text: str,
    kokoro_chinese: Any,
    g2p_chinese: Any,
    voice: Optional[str] = None,
    english_voice: Optional[str] = None,
    speed: float = 1.0,
    sample_rate: int = 24000,
    min_en_merge_len: int = 2
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Create an async generator that yields audio chunks for mixed Chinese/English text.
    
    This function:
    1. Segments the input text into Chinese and English parts
    2. Routes each segment to the appropriate TTS model (kokoro_chinese or kokoro_english)
    3. Yields audio chunks progressively as they are generated
    
    Args:
        text: Input text containing mixed Chinese and English
        kokoro_chinese: The Chinese Kokoro model instance (from main.py)
        g2p_chinese: The Chinese G2P converter instance (from main.py)
        voice: Voice name for Chinese TTS (default: "zf_001")
        english_voice: Voice name for English TTS (default: "af_heart")
        speed: Speech speed multiplier (default: 1.0)
        sample_rate: Target sample rate (default: 24000)
        min_en_merge_len: Minimum length for standalone English segments (default: 2)
                         Shorter English segments are handled by Chinese TTS
    
    Yields:
        Tuple of (audio_samples as numpy array, sample_rate)
    """
    if not text or not text.strip():
        return
    
    # Set default voices
    chinese_voice = voice or DEFAULT_CHINESE_VOICE
    eng_voice = english_voice or DEFAULT_ENGLISH_VOICE
    
    # Split text into language segments
    segments = split_text_into_segments(text, min_en_merge_len=min_en_merge_len)
    
    if not segments:
        return
    
    logger.info(f"Mixed stream: {len(segments)} segments from text length {len(text)}")
    
    # Check if English model is available
    english_available = is_english_model_available()
    if not english_available:
        logger.warning("English TTS model not available, falling back to Chinese TTS for all segments")
    
    # Process each segment sequentially
    for idx, (lang, segment_text) in enumerate(segments):
        if not segment_text or not segment_text.strip():
            continue
        
        logger.debug(f"Processing segment {idx+1}/{len(segments)}: lang={lang}, text='{segment_text[:50]}...'")
        
        try:
            if lang == 'en' and english_available:
                # Use English TTS
                async for chunk in create_english_stream(
                    segment_text,
                    voice=eng_voice,
                    speed=speed,
                    sample_rate=sample_rate
                ):
                    yield chunk
            else:
                # Use Chinese TTS (also handles short English segments)
                async for chunk in _create_chinese_stream(
                    segment_text,
                    kokoro_chinese,
                    g2p_chinese,
                    voice=chinese_voice,
                    speed=speed,
                    sample_rate=sample_rate
                ):
                    yield chunk
        except Exception as e:
            logger.exception(f"Error processing segment {idx+1}: {e}")
            # Continue with next segment instead of failing completely
            continue
    
    logger.debug("Mixed stream completed")


async def _create_chinese_stream(
    text: str,
    kokoro_chinese: Any,
    g2p_chinese: Any,
    voice: str,
    speed: float,
    sample_rate: int
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Create an async generator for Chinese text using the provided model instances.
    
    This is a helper function that wraps the Chinese Kokoro model's create_stream method.
    """
    if not text or not text.strip():
        return
    
    try:
        # Convert text to phonemes using Chinese G2P
        phonemes, _ = g2p_chinese(text)
    except Exception as e:
        logger.exception(f"Chinese G2P conversion failed for text: {text[:100]}")
        raise RuntimeError(f"Chinese G2P conversion failed: {e}")
    
    try:
        # Use streaming mode
        if hasattr(kokoro_chinese, 'create_stream'):
            stream = kokoro_chinese.create_stream(
                phonemes,
                voice=voice,
                speed=speed,
                is_phonemes=True
            )
            
            async for audio_chunk, sr in stream:
                yield (audio_chunk, sr)
        else:
            # Fallback to non-streaming create
            samples, sr = kokoro_chinese.create(
                phonemes,
                voice=voice,
                speed=speed,
                is_phonemes=True
            )
            yield (samples, sr)
            
    except Exception as e:
        logger.exception(f"Chinese TTS synthesis failed for text: {text[:100]}")
        raise RuntimeError(f"Chinese TTS synthesis failed: {e}")


async def create_mixed_stream_with_phonemes(
    text: str,
    phonemes: str,
    kokoro_chinese: Any,
    voice: Optional[str] = None,
    english_voice: Optional[str] = None,
    speed: float = 1.0,
    sample_rate: int = 24000
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Alternative mixed stream that accepts pre-computed phonemes.
    
    This is useful when the caller has already done G2P conversion
    and wants to use the phonemes directly for the main text,
    but still wants mixed language support.
    
    Note: This function assumes the phonemes are for Chinese text.
    For pure Chinese text with pre-computed phonemes, this just wraps
    the Chinese TTS model.
    
    Args:
        text: Original text (used for logging and fallback detection)
        phonemes: Pre-computed phonemes for Chinese TTS
        kokoro_chinese: The Chinese Kokoro model instance
        voice: Voice name for Chinese TTS
        english_voice: Voice name for English TTS (not used when phonemes provided)
        speed: Speech speed multiplier
        sample_rate: Target sample rate
    
    Yields:
        Tuple of (audio_samples as numpy array, sample_rate)
    """
    if not phonemes:
        return
    
    chinese_voice = voice or DEFAULT_CHINESE_VOICE
    
    try:
        if hasattr(kokoro_chinese, 'create_stream'):
            stream = kokoro_chinese.create_stream(
                phonemes,
                voice=chinese_voice,
                speed=speed,
                is_phonemes=True
            )
            
            async for audio_chunk, sr in stream:
                yield (audio_chunk, sr)
        else:
            samples, sr = kokoro_chinese.create(
                phonemes,
                voice=chinese_voice,
                speed=speed,
                is_phonemes=True
            )
            yield (samples, sr)
            
    except Exception as e:
        logger.exception(f"Mixed stream with phonemes failed: {e}")
        raise


def check_mixed_stream_availability() -> dict:
    """
    Check the availability of TTS models for mixed streaming.
    
    Returns a dict with status information:
    {
        'chinese_available': bool,  # Always True if this module loads
        'english_available': bool,  # True if English model is loaded
        'message': str
    }
    """
    english_available = is_english_model_available()
    
    return {
        'chinese_available': True,
        'english_available': english_available,
        'message': 'Both Chinese and English TTS available' if english_available 
                   else 'Only Chinese TTS available (English will use Chinese model)'
    }
