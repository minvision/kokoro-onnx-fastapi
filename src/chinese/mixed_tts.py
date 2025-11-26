"""
Mixed TTS module for handling Chinese-English mixed text.
Segments text by language and synthesizes each segment with the appropriate TTS model,
then concatenates the results in order.
"""

import asyncio
import logging
from typing import Optional, Tuple, List, AsyncIterator, Union
import numpy as np

# Handle both relative and absolute imports
try:
    from .utils import (
        segment_by_language,
        merge_short_segments,
        clean_segment_text,
        ensure_mono,
        resample_linear,
        concatenate_audio,
        float_to_int16_bytes
    )
except ImportError:
    from utils import (
        segment_by_language,
        merge_short_segments,
        clean_segment_text,
        ensure_mono,
        resample_linear,
        concatenate_audio,
        float_to_int16_bytes
    )

logger = logging.getLogger(__name__)

# Target sample rate for mixed output (use Chinese model's rate as default)
DEFAULT_SAMPLE_RATE = 24000

# Default English voice for mixed TTS
DEFAULT_ENGLISH_VOICE = "af_heart"


class MixedTTS:
    """
    Mixed Chinese-English TTS synthesizer.
    
    Handles text that contains both Chinese and English,
    segmenting by language and using appropriate TTS model for each segment.
    """
    
    def __init__(
        self,
        chinese_model=None,
        chinese_g2p=None,
        english_model=None,
        english_g2p=None,
        target_sample_rate: int = DEFAULT_SAMPLE_RATE
    ):
        """
        Initialize MixedTTS with model instances.
        
        Args:
            chinese_model: Kokoro model instance for Chinese
            chinese_g2p: Chinese G2P converter instance
            english_model: Kokoro model instance for English (optional, will lazy load)
            english_g2p: English G2P converter instance (optional, will lazy load)
            target_sample_rate: Target sample rate for output audio
        """
        self.chinese_model = chinese_model
        self.chinese_g2p = chinese_g2p
        self.english_model = english_model
        self.english_g2p = english_g2p
        self.target_sample_rate = target_sample_rate
        
        # English TTS lazy loading flag
        self._english_loaded = english_model is not None
    
    def _ensure_english_loaded(self) -> bool:
        """Ensure English TTS components are loaded."""
        if self._english_loaded:
            return True
        
        try:
            try:
                from . import english_tts
            except ImportError:
                import english_tts
            if not english_tts.is_english_model_loaded():
                if not english_tts.load_english_model():
                    logger.warning("Failed to load English TTS model")
                    return False
            
            self._english_loaded = True
            return True
            
        except Exception as e:
            logger.warning(f"Failed to initialize English TTS: {e}")
            return False
    
    def _synthesize_chinese_segment(
        self,
        text: str,
        voice: str,
        speed: float
    ) -> Optional[Tuple[np.ndarray, int]]:
        """
        Synthesize Chinese text segment.
        
        Args:
            text: Chinese text
            voice: Chinese voice name
            speed: Speech speed
            
        Returns:
            Tuple of (samples, sample_rate) or None
        """
        if not self.chinese_model or not self.chinese_g2p:
            logger.error("Chinese TTS model not initialized")
            return None
        
        try:
            phonemes, _ = self.chinese_g2p(text)
            samples, sample_rate = self.chinese_model.create(
                phonemes,
                voice=voice,
                speed=speed,
                is_phonemes=True
            )
            return samples, sample_rate
            
        except Exception as e:
            logger.exception(f"Chinese TTS synthesis failed: {e}")
            return None
    
    def _synthesize_english_segment(
        self,
        text: str,
        voice: str,
        speed: float
    ) -> Optional[Tuple[np.ndarray, int]]:
        """
        Synthesize English text segment.
        
        Args:
            text: English text
            voice: English voice name (or will use default)
            speed: Speech speed
            
        Returns:
            Tuple of (samples, sample_rate) or None
        """
        try:
            try:
                from . import english_tts
            except ImportError:
                import english_tts
            
            if not self._ensure_english_loaded():
                # Fallback: try to pronounce English with Chinese model
                logger.warning("English model not available, using Chinese model fallback")
                return self._synthesize_chinese_segment(text, voice, speed)
            
            # Use default English voice if a Chinese voice was provided
            english_voice = voice
            if voice.startswith("zf_") or voice.startswith("zm_"):
                english_voice = english_tts.get_default_english_voice()
            
            result = english_tts.synthesize_english(text, english_voice, speed)
            return result
            
        except Exception as e:
            logger.exception(f"English TTS synthesis failed: {e}")
            return None
    
    def synthesize(
        self,
        text: str,
        voice: str = "zf_001",
        english_voice: Optional[str] = None,
        speed: float = 1.0,
        merge_threshold: int = 2
    ) -> Optional[Tuple[np.ndarray, int]]:
        """
        Synthesize mixed Chinese-English text.
        
        Args:
            text: Input text (can be Chinese, English, or mixed)
            voice: Chinese voice name
            english_voice: English voice name (if different from default)
            speed: Speech speed
            merge_threshold: Minimum segment length before merging
            
        Returns:
            Tuple of (audio_samples, sample_rate) or None
        """
        # Segment text by language
        segments = segment_by_language(text)
        
        if not segments:
            logger.warning("No segments to synthesize")
            return None
        
        # Merge short segments to reduce language switching
        segments = merge_short_segments(segments, merge_threshold)
        
        logger.info(f"Mixed TTS: {len(segments)} segments to synthesize")
        
        # Synthesize each segment
        audio_parts: List[Tuple[np.ndarray, int]] = []
        
        for segment_text, lang in segments:
            segment_text = clean_segment_text(segment_text)
            if not segment_text:
                continue
            
            logger.debug(f"Synthesizing segment: lang={lang}, text='{segment_text[:50]}...'")
            
            if lang == 'zh':
                result = self._synthesize_chinese_segment(segment_text, voice, speed)
            else:  # 'en'
                voice_to_use = english_voice or DEFAULT_ENGLISH_VOICE
                result = self._synthesize_english_segment(segment_text, voice_to_use, speed)
            
            if result:
                audio_parts.append(result)
            else:
                logger.warning(f"Failed to synthesize segment: {segment_text[:50]}...")
        
        if not audio_parts:
            logger.error("All segments failed to synthesize")
            return None
        
        # Concatenate all audio parts
        combined_samples, sample_rate = concatenate_audio(
            audio_parts,
            self.target_sample_rate
        )
        
        return combined_samples, sample_rate
    
    async def create_stream(
        self,
        text: str,
        voice: str = "zf_001",
        english_voice: Optional[str] = None,
        speed: float = 1.0,
        merge_threshold: int = 2
    ) -> AsyncIterator[Tuple[np.ndarray, int]]:
        """
        Create a streaming generator for mixed TTS.
        Yields audio chunks as they are synthesized.
        
        Args:
            text: Input text (can be Chinese, English, or mixed)
            voice: Chinese voice name
            english_voice: English voice name (if different from default)
            speed: Speech speed
            merge_threshold: Minimum segment length before merging
            
        Yields:
            Tuples of (audio_chunk, sample_rate)
        """
        # Segment text by language
        segments = segment_by_language(text)
        
        if not segments:
            logger.warning("No segments to synthesize")
            return
        
        # Merge short segments
        segments = merge_short_segments(segments, merge_threshold)
        
        logger.info(f"Mixed TTS stream: {len(segments)} segments")
        
        for segment_text, lang in segments:
            segment_text = clean_segment_text(segment_text)
            if not segment_text:
                continue
            
            logger.debug(f"Streaming segment: lang={lang}")
            
            try:
                if lang == 'zh':
                    # Use Chinese model streaming
                    if self.chinese_model and self.chinese_g2p:
                        phonemes, _ = self.chinese_g2p(segment_text)
                        stream = self.chinese_model.create_stream(
                            phonemes,
                            voice=voice,
                            speed=speed,
                            is_phonemes=True
                        )
                        async for chunk, sr in stream:
                            yield chunk, sr
                else:
                    # Use English model streaming
                    try:
                        from . import english_tts
                    except ImportError:
                        import english_tts
                    
                    if self._ensure_english_loaded():
                        voice_to_use = english_voice or DEFAULT_ENGLISH_VOICE
                        stream = english_tts.create_english_stream(
                            segment_text,
                            voice_to_use,
                            speed
                        )
                        if stream:
                            async for chunk, sr in stream:
                                yield chunk, sr
                    else:
                        # Fallback to non-streaming synthesis
                        result = self._synthesize_english_segment(
                            segment_text,
                            english_voice or DEFAULT_ENGLISH_VOICE,
                            speed
                        )
                        if result:
                            yield result
                            
            except Exception as e:
                logger.exception(f"Error streaming segment: {e}")
                continue


async def create_mixed_tts_stream(
    text: str,
    chinese_model,
    chinese_g2p,
    voice: str = "zf_001",
    english_voice: Optional[str] = None,
    speed: float = 1.0,
    target_sample_rate: int = DEFAULT_SAMPLE_RATE
) -> AsyncIterator[Tuple[np.ndarray, int]]:
    """
    Convenience function to create a mixed TTS stream.
    
    Args:
        text: Input text
        chinese_model: Chinese Kokoro model
        chinese_g2p: Chinese G2P converter
        voice: Chinese voice name
        english_voice: English voice name (optional)
        speed: Speech speed
        target_sample_rate: Target output sample rate
        
    Yields:
        Tuples of (audio_chunk, sample_rate)
    """
    mixer = MixedTTS(
        chinese_model=chinese_model,
        chinese_g2p=chinese_g2p,
        target_sample_rate=target_sample_rate
    )
    
    async for chunk, sr in mixer.create_stream(
        text,
        voice=voice,
        english_voice=english_voice,
        speed=speed
    ):
        yield chunk, sr


def detect_language_mix(text: str) -> dict:
    """
    Analyze text for language composition.
    
    Args:
        text: Input text
        
    Returns:
        Dictionary with analysis results:
        {
            'has_chinese': bool,
            'has_english': bool,
            'is_mixed': bool,
            'segment_count': int,
            'chinese_ratio': float,
            'english_ratio': float
        }
    """
    segments = segment_by_language(text)
    
    if not segments:
        return {
            'has_chinese': False,
            'has_english': False,
            'is_mixed': False,
            'segment_count': 0,
            'chinese_ratio': 0.0,
            'english_ratio': 0.0
        }
    
    chinese_chars = sum(len(s) for s, lang in segments if lang == 'zh')
    english_chars = sum(len(s) for s, lang in segments if lang == 'en')
    total_chars = chinese_chars + english_chars
    
    has_chinese = chinese_chars > 0
    has_english = english_chars > 0
    
    return {
        'has_chinese': has_chinese,
        'has_english': has_english,
        'is_mixed': has_chinese and has_english,
        'segment_count': len(segments),
        'chinese_ratio': chinese_chars / total_chars if total_chars > 0 else 0.0,
        'english_ratio': english_chars / total_chars if total_chars > 0 else 0.0
    }
