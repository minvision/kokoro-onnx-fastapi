"""
Mixed stream synthesizer for Chinese/English mixed text.

This module provides a unified streaming interface that handles both Chinese
and English text segments, producing a continuous audio stream by switching
between the appropriate TTS models for each segment.
"""

import logging
from typing import Optional, AsyncGenerator, Tuple, Dict, Any
import numpy as np

from .lang_split import split_by_language
from .english_tts import (
    create_english_stream,
    initialize_english_model,
    is_english_model_ready,
    get_default_english_voice
)

logger = logging.getLogger(__name__)

# Sample rate constants
CHINESE_SAMPLE_RATE = 24000  # kokoro v1.1-zh output sample rate
ENGLISH_SAMPLE_RATE = 24000  # kokoro v1.0 output sample rate


async def create_mixed_stream(
    text: str,
    kokoro_model,
    g2p_converter,
    voice: str = "zf_001",
    english_voice: Optional[str] = None,
    speed: float = 1.0,
    **kwargs
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Create an async generator for mixed Chinese/English TTS streaming.
    
    This function splits the input text into Chinese and English segments,
    then synthesizes each segment using the appropriate TTS model (Chinese or English),
    yielding audio chunks as they are produced.
    
    Args:
        text: Mixed Chinese/English text to synthesize.
        kokoro_model: The Chinese Kokoro model instance.
        g2p_converter: The Chinese G2P converter.
        voice: Voice model for Chinese synthesis (default: zf_001).
        english_voice: Voice model for English synthesis (default: af_heart).
        speed: Speech speed multiplier.
        **kwargs: Additional arguments (reserved for future use).
    
    Yields:
        Tuples of (audio_samples, sample_rate) where audio_samples is a numpy array
        of float32 samples.
    
    Raises:
        RuntimeError: If models are not properly initialized.
    """
    if kokoro_model is None:
        raise RuntimeError("Chinese model not initialized")
    
    if g2p_converter is None:
        raise RuntimeError("Chinese G2P converter not initialized")
    
    # Initialize English model if needed
    if not is_english_model_ready():
        if not initialize_english_model():
            logger.warning("English model initialization failed, English segments will use Chinese model")
    
    # Set default English voice
    if english_voice is None:
        english_voice = get_default_english_voice()
    
    # Split text into language segments
    segments = split_by_language(text)
    
    if not segments:
        logger.warning("No segments to synthesize from input text")
        return
    
    logger.debug(f"Split text into {len(segments)} segments: {[(s[0], s[1][:20]+'...' if len(s[1])>20 else s[1]) for s in segments]}")
    
    for lang, segment_text in segments:
        segment_text = segment_text.strip()
        if not segment_text:
            continue
        
        try:
            if lang == 'en' and is_english_model_ready():
                # Use English TTS
                logger.debug(f"Synthesizing English segment: {segment_text[:50]}...")
                async for audio_chunk, sample_rate in create_english_stream(
                    segment_text,
                    voice=english_voice,
                    speed=speed
                ):
                    yield audio_chunk, sample_rate
            else:
                # Use Chinese TTS (also as fallback for English if model not available)
                logger.debug(f"Synthesizing Chinese segment: {segment_text[:50]}...")
                try:
                    phonemes, _ = g2p_converter(segment_text)
                    stream_gen = kokoro_model.create_stream(
                        phonemes,
                        voice=voice,
                        speed=speed,
                        is_phonemes=True
                    )
                    async for audio_chunk, sample_rate in stream_gen:
                        yield audio_chunk, sample_rate
                except Exception as e:
                    logger.exception(f"Failed to synthesize Chinese segment: {e}")
                    raise
                    
        except Exception as e:
            logger.exception(f"Error synthesizing segment ({lang}): {segment_text[:50]}...")
            # Continue to next segment instead of failing completely
            continue


async def create_mixed_stream_with_config(
    text: str,
    model_cfg: Dict[str, Any],
    **kwargs
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Create a mixed stream using a configuration dictionary.
    
    This is an alternative interface that accepts model configuration
    as a dictionary, which can be useful for dynamic configuration.
    
    Args:
        text: Mixed Chinese/English text to synthesize.
        model_cfg: Configuration dictionary containing:
            - kokoro_model: Chinese Kokoro model instance
            - g2p_converter: Chinese G2P converter
            - voice: Chinese voice (optional, default: zf_001)
            - english_voice: English voice (optional, default: af_heart)
            - speed: Speech speed (optional, default: 1.0)
        **kwargs: Additional arguments passed to create_mixed_stream.
    
    Yields:
        Tuples of (audio_samples, sample_rate).
    """
    kokoro_model = model_cfg.get('kokoro_model')
    g2p_converter = model_cfg.get('g2p_converter')
    voice = model_cfg.get('voice', 'zf_001')
    english_voice = model_cfg.get('english_voice')
    speed = model_cfg.get('speed', 1.0)
    
    async for audio_chunk, sample_rate in create_mixed_stream(
        text=text,
        kokoro_model=kokoro_model,
        g2p_converter=g2p_converter,
        voice=voice,
        english_voice=english_voice,
        speed=speed,
        **kwargs
    ):
        yield audio_chunk, sample_rate


def detect_language_segments(text: str) -> list:
    """
    Utility function to preview language segments without synthesizing.
    
    Args:
        text: Text to analyze.
    
    Returns:
        List of tuples (language, text) showing how text would be split.
    """
    return split_by_language(text)
