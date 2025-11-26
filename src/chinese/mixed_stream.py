"""
mixed_stream.py - Mixed Language Streaming Module

Implements create_mixed_stream() which handles mixed Chinese/English text
by splitting it into segments and streaming audio from the appropriate TTS engine.
"""

import logging
import asyncio
from typing import Optional, AsyncGenerator, Tuple, Any

import numpy as np

from .lang_split import split_text_by_language
from .english_tts import create_english_stream

logger = logging.getLogger(__name__)

# Default sample rate for output
DEFAULT_SAMPLE_RATE = 24000


async def _normalize_stream(
    stream_result: Any
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Normalize various stream result types to async generator.
    
    Handles:
    - Coroutine returning async generator
    - Async generator directly
    - Sync generator
    - Single result tuple (samples, sr)
    
    Args:
        stream_result: The result from kokoro.create_stream()
        
    Yields:
        Tuple of (audio_samples, sample_rate)
    """
    # If it's a coroutine, await it first
    if asyncio.iscoroutine(stream_result):
        stream_result = await stream_result
    
    # Now handle the actual result type
    if hasattr(stream_result, '__anext__'):
        # Async generator
        async for chunk, sr in stream_result:
            yield (np.asarray(chunk, dtype=np.float32), int(sr))
    elif hasattr(stream_result, '__next__'):
        # Sync generator - wrap in async
        for chunk, sr in stream_result:
            yield (np.asarray(chunk, dtype=np.float32), int(sr))
            await asyncio.sleep(0)  # Yield control to event loop
    else:
        # Assume it's a single result tuple (samples, sr)
        samples, sr = stream_result
        yield (np.asarray(samples, dtype=np.float32), int(sr))


async def create_chinese_segment_stream(
    text: str,
    kokoro_model: Any,
    g2p_converter: Any,
    voice: Optional[str] = None,
    speed: float = 1.0
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Create audio stream for a Chinese text segment.
    
    Args:
        text: Chinese text to synthesize
        kokoro_model: The Chinese Kokoro model instance
        g2p_converter: The Chinese G2P converter
        voice: Voice name (e.g., 'zf_001')
        speed: Speech speed
        
    Yields:
        Tuple of (audio_samples, sample_rate)
    """
    if kokoro_model is None or g2p_converter is None:
        raise RuntimeError("Chinese TTS model is not available")
    
    # Default Chinese voice
    if voice is None:
        voice = "zf_001"
    
    # Convert to phonemes
    try:
        phonemes, _ = g2p_converter(text)
    except Exception as e:
        logger.exception(f"Chinese G2P conversion failed for text: {text[:100]}...")
        raise RuntimeError(f"Chinese G2P conversion failed: {e}")
    
    # Create stream
    try:
        stream_result = kokoro_model.create_stream(
            phonemes,
            voice=voice,
            speed=speed,
            is_phonemes=True
        )
        
        async for chunk, sr in _normalize_stream(stream_result):
            yield (chunk, sr)
            
    except Exception as e:
        logger.exception(f"Chinese TTS stream creation failed: {e}")
        raise RuntimeError(f"Chinese TTS stream creation failed: {e}")


async def create_mixed_stream(
    text: str,
    kokoro_model: Any,
    g2p_converter: Any,
    voice_zh: Optional[str] = None,
    voice_en: Optional[str] = None,
    speed: float = 1.0,
    sample_rate: int = DEFAULT_SAMPLE_RATE
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Create an async generator that yields audio chunks for mixed Chinese/English text.
    
    This function:
    1. Splits the input text into Chinese and English segments
    2. For each segment, calls the appropriate TTS engine
    3. Yields audio chunks as they are generated (streaming)
    
    Args:
        text: Mixed Chinese/English text to synthesize
        kokoro_model: The Chinese Kokoro model instance (from main.py)
        g2p_converter: The Chinese G2P converter (from main.py)
        voice_zh: Chinese voice name (default: 'zf_001')
        voice_en: English voice name (default: 'af_heart')
        speed: Speech speed (default: 1.0)
        sample_rate: Target sample rate (default: 24000)
        
    Yields:
        Tuple of (audio_samples: np.ndarray, sample_rate: int)
        
    Example:
        >>> async for samples, sr in create_mixed_stream("你好Hello世界", model, g2p):
        ...     process_audio(samples, sr)
    """
    if not text or not text.strip():
        logger.warning("Empty text provided to create_mixed_stream")
        return
    
    # Split text into language segments
    segments = split_text_by_language(text, merge_short=True)
    
    if not segments:
        logger.warning(f"No segments produced from text: {text[:100]}...")
        return
    
    logger.info(f"Mixed stream: Processing {len(segments)} segment(s)")
    
    for idx, (lang, segment_text) in enumerate(segments):
        segment_text = segment_text.strip()
        if not segment_text:
            continue
            
        logger.debug(f"Segment {idx+1}/{len(segments)}: lang={lang}, text={segment_text[:50]}...")
        
        try:
            if lang == 'zh':
                # Chinese segment - use the Chinese Kokoro model
                async for chunk, sr in create_chinese_segment_stream(
                    segment_text,
                    kokoro_model,
                    g2p_converter,
                    voice=voice_zh,
                    speed=speed
                ):
                    yield (chunk, sr)
                    
            else:  # lang == 'en'
                # English segment - use the English TTS wrapper
                async for chunk, sr in create_english_stream(
                    segment_text,
                    voice=voice_en,
                    speed=speed,
                    sample_rate=sample_rate
                ):
                    yield (chunk, sr)
                    
        except Exception as e:
            logger.exception(f"Failed to process segment {idx+1} (lang={lang}): {e}")
            # Continue with next segment instead of failing completely
            continue
    
    logger.info(f"Mixed stream completed for text: {text[:50]}...")
