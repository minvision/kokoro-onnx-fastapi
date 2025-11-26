"""
Utility functions for mixed Chinese/English TTS.
Includes:
- Language segmentation (Chinese vs English/ASCII)
- Audio format helpers
- PCM/WAV utilities
"""

import re
import numpy as np
from typing import List, Tuple


def is_ascii_char(char: str) -> bool:
    """Check if a character is ASCII (0x00-0x7F)."""
    return ord(char) <= 0x7F


def segment_by_language(text: str) -> List[Tuple[str, str]]:
    """
    Segment text into chunks of continuous Chinese or English/ASCII.
    
    Returns a list of tuples: (segment_text, language)
    where language is 'zh' for Chinese, 'en' for English/ASCII.
    
    Strategy:
    - Consecutive ASCII characters (including punctuation, numbers, spaces) -> 'en'
    - Consecutive non-ASCII characters (Chinese, etc.) -> 'zh'
    - Preserves boundaries at language transitions
    - Adjacent quotes, brackets around text are kept with their content
    
    Args:
        text: Input text potentially containing mixed languages
        
    Returns:
        List of (segment, language_code) tuples
    """
    if not text:
        return []
    
    segments = []
    current_segment = ""
    current_lang = None
    
    for char in text:
        # Determine language of this character
        if is_ascii_char(char):
            char_lang = 'en'
        else:
            char_lang = 'zh'
        
        # Handle transitions
        if current_lang is None:
            current_lang = char_lang
            current_segment = char
        elif char_lang == current_lang:
            current_segment += char
        else:
            # Language transition - save current segment and start new one
            if current_segment.strip():  # Only add non-empty segments
                segments.append((current_segment, current_lang))
            current_segment = char
            current_lang = char_lang
    
    # Add final segment
    if current_segment.strip():
        segments.append((current_segment, current_lang))
    
    return segments


def merge_short_segments(segments: List[Tuple[str, str]], 
                         min_length: int = 2) -> List[Tuple[str, str]]:
    """
    Merge very short segments (like single punctuation) with adjacent segments
    to avoid excessive language switching.
    
    Args:
        segments: List of (text, language) tuples
        min_length: Minimum length threshold for standalone segment
        
    Returns:
        Merged list of segments
    """
    if len(segments) <= 1:
        return segments
    
    merged = []
    i = 0
    
    while i < len(segments):
        text, lang = segments[i]
        
        # If this is a very short segment (like punctuation)
        if len(text.strip()) < min_length and i > 0 and merged:
            # Try to merge with previous segment
            prev_text, prev_lang = merged[-1]
            merged[-1] = (prev_text + text, prev_lang)
        elif len(text.strip()) < min_length and i < len(segments) - 1:
            # Merge with next segment
            next_text, next_lang = segments[i + 1]
            segments[i + 1] = (text + next_text, next_lang)
        else:
            merged.append((text, lang))
        
        i += 1
    
    return merged


def clean_segment_text(text: str) -> str:
    """
    Clean up a segment text by removing excessive whitespace
    while preserving necessary spacing.
    
    Args:
        text: Input text segment
        
    Returns:
        Cleaned text
    """
    # Replace multiple spaces/newlines with single space
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def ensure_mono(samples: np.ndarray) -> np.ndarray:
    """
    Ensure audio samples are mono (single channel).
    
    Args:
        samples: Audio samples array
        
    Returns:
        Mono audio samples
    """
    samples = np.asarray(samples)
    if samples.ndim == 1:
        return samples
    # Multi-channel: average to mono
    return samples.mean(axis=1)


def resample_linear(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """
    Resample audio using linear interpolation.
    
    Args:
        samples: Input audio samples
        orig_sr: Original sample rate
        target_sr: Target sample rate
        
    Returns:
        Resampled audio samples
    """
    if orig_sr == target_sr:
        return samples
    
    samples = np.asarray(samples)
    duration = samples.shape[0] / float(orig_sr)
    new_len = max(1, int(round(duration * target_sr)))
    
    if new_len == samples.shape[0]:
        return samples
    
    old_idx = np.linspace(0, samples.shape[0] - 1, samples.shape[0])
    new_idx = np.linspace(0, samples.shape[0] - 1, new_len)
    res = np.interp(new_idx, old_idx, samples).astype(samples.dtype)
    return res


def float_to_int16_bytes(samples: np.ndarray) -> bytes:
    """
    Convert float audio samples to 16-bit PCM bytes.
    
    Args:
        samples: Float audio samples in range [-1.0, 1.0]
        
    Returns:
        16-bit little-endian PCM bytes
    """
    clipped = np.clip(samples, -1.0, 1.0)
    int16 = (clipped * 32767.0).astype(np.int16)
    # Ensure little-endian byte order
    int16_le = int16.astype('<i2')  # '<i2' specifies little-endian 2-byte integer
    return int16_le.tobytes()


def int16_bytes_to_float(pcm_bytes: bytes) -> np.ndarray:
    """
    Convert 16-bit PCM bytes to float samples.
    
    Args:
        pcm_bytes: 16-bit little-endian PCM bytes
        
    Returns:
        Float audio samples in range [-1.0, 1.0]
    """
    int16_arr = np.frombuffer(pcm_bytes, dtype=np.int16)
    return int16_arr.astype(np.float32) / 32767.0


def concatenate_audio(audio_parts: List[Tuple[np.ndarray, int]], 
                      target_sr: int = 24000) -> Tuple[np.ndarray, int]:
    """
    Concatenate multiple audio parts, resampling if necessary.
    
    Args:
        audio_parts: List of (samples, sample_rate) tuples
        target_sr: Target sample rate for output
        
    Returns:
        Tuple of (concatenated_samples, sample_rate)
    """
    if not audio_parts:
        return np.array([], dtype=np.float32), target_sr
    
    resampled_parts = []
    for samples, sr in audio_parts:
        samples = ensure_mono(samples)
        if sr != target_sr:
            samples = resample_linear(samples, sr, target_sr)
        resampled_parts.append(samples.astype(np.float32))
    
    if len(resampled_parts) == 1:
        return resampled_parts[0], target_sr
    
    return np.concatenate(resampled_parts), target_sr


def validate_sample_rate(sample_rate: int) -> bool:
    """
    Validate if sample rate is supported.
    
    Args:
        sample_rate: Sample rate to validate
        
    Returns:
        True if valid, False otherwise
    """
    valid_rates = [8000, 16000, 22050, 24000, 44100, 48000]
    return sample_rate in valid_rates


def estimate_audio_duration(samples: np.ndarray, sample_rate: int) -> float:
    """
    Estimate audio duration in seconds.
    
    Args:
        samples: Audio samples
        sample_rate: Sample rate
        
    Returns:
        Duration in seconds
    """
    return len(samples) / sample_rate
