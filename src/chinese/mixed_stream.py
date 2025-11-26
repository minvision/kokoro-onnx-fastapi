"""
Mixed text stream synthesizer for Chinese-English mixed content.

This module provides functionality to synthesize mixed Chinese-English text
by splitting the text into language segments and routing each segment to
the appropriate TTS model (Chinese or English).

The output is a unified async generator that produces audio chunks compatible
with the existing stream_rtp_from_asyncgen interface.
"""

import logging
from typing import AsyncGenerator, Tuple, Optional, Callable, Any

import numpy as np

from .lang_split import segment_text

logger = logging.getLogger(__name__)

# Default voice settings
DEFAULT_ZH_VOICE = "zf_001"
DEFAULT_EN_VOICE = "af_heart"


async def create_mixed_stream(
    text: str,
    zh_voice: str = DEFAULT_ZH_VOICE,
    en_voice: str = DEFAULT_EN_VOICE,
    speed: float = 1.0,
    zh_model = None,
    zh_g2p = None,
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Create an async generator stream from mixed Chinese-English text.
    
    This function:
    1. Segments the text into Chinese and English parts
    2. Routes each segment to the appropriate TTS model
    3. Yields audio chunks sequentially, maintaining order
    
    Args:
        text: Mixed Chinese-English text to synthesize.
        zh_voice: Chinese voice name (default: zf_001).
        en_voice: English voice name (default: af_heart).
        speed: Speech speed multiplier (default: 1.0).
        zh_model: Chinese Kokoro model instance (required).
        zh_g2p: Chinese G2P converter instance (required).
        
    Yields:
        Tuples of (audio_samples, sample_rate) as audio is generated.
        
    Raises:
        ValueError: If Chinese model/g2p are not provided.
    """
    if zh_model is None or zh_g2p is None:
        raise ValueError("Chinese model (zh_model) and G2P converter (zh_g2p) are required")
    
    if not text or not text.strip():
        logger.warning("Empty text provided to create_mixed_stream")
        return
    
    # Segment the text by language
    segments = segment_text(text)
    
    if not segments:
        logger.warning("No segments generated from text")
        return
    
    logger.info(f"Mixed stream: processing {len(segments)} segments")
    
    for i, (segment_text_content, lang) in enumerate(segments):
        # Skip empty segments
        if not segment_text_content or not segment_text_content.strip():
            continue
            
        logger.debug(f"Processing segment {i+1}/{len(segments)}: lang={lang}, text={segment_text_content[:50]}...")
        
        if lang == 'zh':
            # Process Chinese segment
            async for chunk in _process_chinese_segment(
                segment_text_content, 
                zh_voice, 
                speed, 
                zh_model, 
                zh_g2p
            ):
                yield chunk
        else:
            # Process English segment
            async for chunk in _process_english_segment(
                segment_text_content, 
                en_voice, 
                speed
            ):
                yield chunk


async def _process_chinese_segment(
    text: str,
    voice: str,
    speed: float,
    model,
    g2p,
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Process a Chinese text segment using the Chinese TTS model.
    
    Args:
        text: Chinese text segment.
        voice: Chinese voice name.
        speed: Speech speed multiplier.
        model: Chinese Kokoro model instance.
        g2p: Chinese G2P converter instance.
        
    Yields:
        Tuples of (audio_samples, sample_rate).
    """
    try:
        # Convert to phonemes using Chinese G2P
        phonemes, _ = g2p(text)
        
        # Create stream from Chinese model
        stream = model.create_stream(phonemes, voice=voice, speed=speed, is_phonemes=True)
        
        # Handle both sync and async generators
        if hasattr(stream, '__anext__'):
            # Async generator
            async for chunk in stream:
                yield chunk
        else:
            # Sync generator - yield from it
            for chunk in stream:
                yield chunk
                
    except Exception as e:
        logger.exception(f"Failed to process Chinese segment: {e}")


async def _process_english_segment(
    text: str,
    voice: str,
    speed: float,
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Process an English text segment using the English TTS model.
    
    Args:
        text: English text segment.
        voice: English voice name.
        speed: Speech speed multiplier.
        
    Yields:
        Tuples of (audio_samples, sample_rate).
    """
    try:
        # Import English TTS adapter
        from .english_tts import create_english_stream
        
        # Create stream from English model
        async for chunk in create_english_stream(text, voice=voice, speed=speed):
            yield chunk
            
    except Exception as e:
        logger.exception(f"Failed to process English segment: {e}")


def create_mixed_stream_generator(
    text: str,
    zh_voice: str = DEFAULT_ZH_VOICE,
    en_voice: str = DEFAULT_EN_VOICE,
    speed: float = 1.0,
    zh_model = None,
    zh_g2p = None,
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Factory function to create a mixed stream generator.
    
    This is a convenience wrapper around create_mixed_stream that returns
    the async generator directly.
    
    Args:
        text: Mixed Chinese-English text to synthesize.
        zh_voice: Chinese voice name (default: zf_001).
        en_voice: English voice name (default: af_heart).
        speed: Speech speed multiplier (default: 1.0).
        zh_model: Chinese Kokoro model instance (required).
        zh_g2p: Chinese G2P converter instance (required).
        
    Returns:
        Async generator yielding (audio_samples, sample_rate) tuples.
    """
    return create_mixed_stream(
        text=text,
        zh_voice=zh_voice,
        en_voice=en_voice,
        speed=speed,
        zh_model=zh_model,
        zh_g2p=zh_g2p,
    )


async def create_mixed_stream_with_fallback(
    text: str,
    zh_voice: str = DEFAULT_ZH_VOICE,
    en_voice: str = DEFAULT_EN_VOICE,
    speed: float = 1.0,
    zh_model = None,
    zh_g2p = None,
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Create a mixed stream with fallback to Chinese-only if English model fails.
    
    This is a more robust version that falls back to Chinese TTS for English
    segments if the English model is not available or fails.
    
    Args:
        text: Mixed Chinese-English text to synthesize.
        zh_voice: Chinese voice name (default: zf_001).
        en_voice: English voice name (default: af_heart).
        speed: Speech speed multiplier (default: 1.0).
        zh_model: Chinese Kokoro model instance (required).
        zh_g2p: Chinese G2P converter instance (required).
        
    Yields:
        Tuples of (audio_samples, sample_rate) as audio is generated.
    """
    if zh_model is None or zh_g2p is None:
        raise ValueError("Chinese model (zh_model) and G2P converter (zh_g2p) are required")
    
    if not text or not text.strip():
        logger.warning("Empty text provided to create_mixed_stream_with_fallback")
        return
    
    # Segment the text by language
    segments = segment_text(text)
    
    if not segments:
        logger.warning("No segments generated from text")
        return
    
    logger.info(f"Mixed stream (with fallback): processing {len(segments)} segments")
    
    for i, (segment_text_content, lang) in enumerate(segments):
        # Skip empty segments
        if not segment_text_content or not segment_text_content.strip():
            continue
        
        logger.debug(f"Processing segment {i+1}/{len(segments)}: lang={lang}, text={segment_text_content[:50]}...")
        
        if lang == 'zh':
            # Process Chinese segment
            async for chunk in _process_chinese_segment(
                segment_text_content, 
                zh_voice, 
                speed, 
                zh_model, 
                zh_g2p
            ):
                yield chunk
        else:
            # Try English first, fall back to Chinese
            try:
                from .english_tts import get_english_model
                en_model, en_g2p = get_english_model()
                
                if en_model is not None and en_g2p is not None:
                    # Use English model
                    async for chunk in _process_english_segment(
                        segment_text_content, 
                        en_voice, 
                        speed
                    ):
                        yield chunk
                else:
                    # Fallback to Chinese model for English text
                    logger.warning(f"English model not available, using Chinese model for: {segment_text_content[:50]}...")
                    async for chunk in _process_chinese_segment(
                        segment_text_content,
                        zh_voice,
                        speed,
                        zh_model,
                        zh_g2p
                    ):
                        yield chunk
            except Exception as e:
                logger.warning(f"English processing failed, falling back to Chinese: {e}")
                async for chunk in _process_chinese_segment(
                    segment_text_content,
                    zh_voice,
                    speed,
                    zh_model,
                    zh_g2p
                ):
                    yield chunk


# Export public API
__all__ = [
    'create_mixed_stream',
    'create_mixed_stream_generator',
    'create_mixed_stream_with_fallback',
    'DEFAULT_ZH_VOICE',
    'DEFAULT_EN_VOICE',
]
