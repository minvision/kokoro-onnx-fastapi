"""
Mixed language stream synthesizer.
Combines Chinese and English TTS to handle mixed language text.
"""
import asyncio
import inspect
import logging
from typing import AsyncGenerator, Tuple, Optional, Any

import numpy as np

from .lang_split import split_by_language

logger = logging.getLogger(__name__)


async def create_mixed_stream(
    text: str,
    voice_zh: str = "zf_001",
    voice_en: str = "af_heart",
    speed: float = 1.0,
    sample_rate: int = 24000,
    min_en_merge_len: int = 3,
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Create an async generator that handles mixed Chinese/English text.
    
    This function splits the text by language and routes each segment to the
    appropriate TTS engine (Chinese or English), yielding audio chunks
    sequentially as they are generated.
    
    Args:
        text: Mixed language text to synthesize.
        voice_zh: Chinese voice name (default 'zf_001').
        voice_en: English voice name (default 'af_heart').
        speed: Speech speed (default 1.0).
        sample_rate: Target sample rate (default 24000).
        min_en_merge_len: Minimum length for standalone English segments.
        
    Yields:
        Tuples of (audio_samples: np.ndarray, sample_rate: int)
    """
    # Import Chinese TTS model
    try:
        from .main import kokoro_model as kokoro_chinese, g2p_converter as zh_g2p
    except ImportError:
        # Handle different import contexts
        import sys
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)
        from main import kokoro_model as kokoro_chinese, g2p_converter as zh_g2p
    
    # Import English TTS adapter
    from .english_tts import create_english_stream
    
    # Split text into language segments
    segments = split_by_language(text, min_en_merge_len=min_en_merge_len)
    logger.debug(f"[mixed_stream] Split text into {len(segments)} segments")
    
    for idx, (lang, segment_text) in enumerate(segments):
        segment_text_stripped = segment_text.strip()
        if not segment_text_stripped:
            continue
            
        logger.debug(f"[mixed_stream] Processing segment {idx+1}/{len(segments)}: lang={lang}, text='{segment_text_stripped[:50]}...'")
        
        try:
            if lang == 'zh':
                # Use Chinese TTS
                async for chunk in _create_chinese_stream(
                    kokoro_chinese, 
                    zh_g2p, 
                    segment_text_stripped, 
                    voice=voice_zh, 
                    speed=speed
                ):
                    yield chunk
            else:
                # Use English TTS
                async for chunk in create_english_stream(
                    segment_text_stripped,
                    voice=voice_en,
                    speed=speed,
                    sample_rate=sample_rate
                ):
                    yield chunk
                    
        except Exception as e:
            logger.exception(f"[mixed_stream] Error processing segment {idx+1}: {e}")
            # Continue with next segment rather than failing completely
            continue


async def _create_chinese_stream(
    kokoro_chinese,
    zh_g2p,
    text: str,
    voice: str = "zf_001",
    speed: float = 1.0,
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Internal helper to create Chinese speech stream.
    
    Args:
        kokoro_chinese: Chinese Kokoro model instance.
        zh_g2p: Chinese G2P converter.
        text: Chinese text to synthesize.
        voice: Voice name.
        speed: Speech speed.
        
    Yields:
        Tuples of (audio_samples: np.ndarray, sample_rate: int)
    """
    if kokoro_chinese is None:
        logger.error("Chinese Kokoro model is not initialized")
        raise RuntimeError("Chinese Kokoro model not initialized")
    
    if zh_g2p is None:
        logger.error("Chinese G2P converter is not initialized")
        raise RuntimeError("Chinese G2P converter not initialized")
    
    try:
        # Convert to phonemes
        phonemes, _ = zh_g2p(text)
        logger.debug(f"[chinese_stream] Converted '{text[:50]}...' to phonemes")
        
        # Check for create_stream method
        if hasattr(kokoro_chinese, 'create_stream'):
            stream_gen = kokoro_chinese.create_stream(
                phonemes,
                voice=voice,
                speed=speed,
                is_phonemes=True
            )
            
            # Handle both async generator and coroutine returning async generator
            if inspect.iscoroutine(stream_gen):
                stream_gen = await stream_gen
            
            async for audio_chunk, sr in stream_gen:
                yield (audio_chunk, sr)
        else:
            # Fallback to synchronous create() method
            logger.debug("[chinese_stream] Using synchronous create() method")
            samples, sr = kokoro_chinese.create(
                phonemes,
                voice=voice,
                speed=speed,
                is_phonemes=True
            )
            yield (samples, sr)
            
    except Exception as e:
        logger.exception(f"[chinese_stream] Error generating Chinese speech: {e}")
        raise


async def create_mixed_stream_with_phonemes(
    text: str,
    zh_phonemes: Optional[str] = None,
    voice_zh: str = "zf_001",
    voice_en: str = "af_heart",
    speed: float = 1.0,
    sample_rate: int = 24000,
) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
    """
    Alternative version that accepts pre-converted Chinese phonemes.
    
    This is useful when the caller has already done G2P conversion
    for the Chinese text portion.
    
    Args:
        text: Original text (used for English portions).
        zh_phonemes: Pre-converted Chinese phonemes.
        voice_zh: Chinese voice name.
        voice_en: English voice name.
        speed: Speech speed.
        sample_rate: Target sample rate.
        
    Yields:
        Tuples of (audio_samples: np.ndarray, sample_rate: int)
    """
    # If phonemes are provided and text is pure Chinese, use them directly
    if zh_phonemes is not None:
        segments = split_by_language(text, min_en_merge_len=0)
        all_chinese = all(lang == 'zh' for lang, _ in segments)
        
        if all_chinese:
            # Use phonemes directly for Chinese
            try:
                from .main import kokoro_model as kokoro_chinese
            except ImportError:
                from main import kokoro_model as kokoro_chinese
            
            if kokoro_chinese is not None and hasattr(kokoro_chinese, 'create_stream'):
                stream_gen = kokoro_chinese.create_stream(
                    zh_phonemes,
                    voice=voice_zh,
                    speed=speed,
                    is_phonemes=True
                )
                
                if inspect.iscoroutine(stream_gen):
                    stream_gen = await stream_gen
                
                async for audio_chunk, sr in stream_gen:
                    yield (audio_chunk, sr)
                return
    
    # Fall back to regular mixed stream
    async for chunk in create_mixed_stream(
        text,
        voice_zh=voice_zh,
        voice_en=voice_en,
        speed=speed,
        sample_rate=sample_rate
    ):
        yield chunk
