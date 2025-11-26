"""
lang_split.py - Language Segmentation Module

Splits input text into segments by language (Chinese/English) based on ASCII/non-ASCII characters.
Also merges short English segments to reduce frequent language switching during TTS synthesis.
"""

from typing import List, Tuple

# Minimum length for standalone English segment (to avoid frequent switching)
MIN_EN_SEGMENT_LENGTH = 3


def is_ascii_char(char: str) -> bool:
    """Check if a character is ASCII (0x00-0x7F)."""
    return ord(char) < 128


def split_by_language(text: str) -> List[Tuple[str, str]]:
    """
    Split text into segments by language based on ASCII/non-ASCII characters.
    
    Args:
        text: Input text containing mixed Chinese and English
        
    Returns:
        List of tuples [(lang, segment), ...] where lang is 'en' or 'zh'
        
    Note:
        - ASCII characters (0x00-0x7F) including English letters, numbers, 
          punctuation are classified as 'en'
        - Non-ASCII characters (Chinese, CJK punctuation, etc.) are classified as 'zh'
    """
    if not text:
        return []
    
    segments: List[Tuple[str, str]] = []
    current_segment = ""
    current_lang = None
    
    for char in text:
        char_lang = 'en' if is_ascii_char(char) else 'zh'
        
        if current_lang is None:
            current_lang = char_lang
            current_segment = char
        elif char_lang == current_lang:
            current_segment += char
        else:
            # Language switch - save current segment and start new one
            if current_segment:
                segments.append((current_lang, current_segment))
            current_lang = char_lang
            current_segment = char
    
    # Don't forget the last segment
    if current_segment:
        segments.append((current_lang, current_segment))
    
    return segments


def merge_short_english_segments(
    segments: List[Tuple[str, str]], 
    min_length: int = MIN_EN_SEGMENT_LENGTH
) -> List[Tuple[str, str]]:
    """
    Merge short English segments into adjacent Chinese segments to reduce switching.
    
    Short English segments (like single punctuation or short words between Chinese text)
    are merged into the preceding or following Chinese segment.
    
    Args:
        segments: List of (lang, text) tuples
        min_length: Minimum length for standalone English segment
        
    Returns:
        List of merged (lang, text) tuples
    """
    if not segments:
        return []
    
    result: List[Tuple[str, str]] = []
    
    i = 0
    while i < len(segments):
        lang, text = segments[i]
        
        # Check if this is a short English segment that should be merged
        if lang == 'en' and len(text.strip()) < min_length:
            # Try to merge with adjacent Chinese segments
            if result and result[-1][0] == 'zh':
                # Merge into preceding Chinese segment
                prev_lang, prev_text = result.pop()
                result.append(('zh', prev_text + text))
            elif i + 1 < len(segments) and segments[i + 1][0] == 'zh':
                # Will be merged with following Chinese segment
                next_lang, next_text = segments[i + 1]
                result.append(('zh', text + next_text))
                i += 1  # Skip the next segment as we've merged it
            else:
                # No adjacent Chinese segment, keep as is
                if result and result[-1][0] == 'en':
                    # Merge with preceding English segment
                    prev_lang, prev_text = result.pop()
                    result.append(('en', prev_text + text))
                else:
                    result.append((lang, text))
        else:
            # Normal segment, check if we can merge with previous same-language segment
            if result and result[-1][0] == lang:
                prev_lang, prev_text = result.pop()
                result.append((lang, prev_text + text))
            else:
                result.append((lang, text))
        
        i += 1
    
    return result


def split_text_by_language(
    text: str, 
    merge_short: bool = True,
    min_en_length: int = MIN_EN_SEGMENT_LENGTH
) -> List[Tuple[str, str]]:
    """
    Main function to split text by language with optional short segment merging.
    
    Args:
        text: Input text containing mixed Chinese and English
        merge_short: Whether to merge short English segments (default: True)
        min_en_length: Minimum length for standalone English segments when merging
        
    Returns:
        List of tuples [(lang, segment), ...] where lang is 'en' or 'zh'
        
    Example:
        >>> split_text_by_language("你好，Hello World！这是一个测试。")
        [('zh', '你好，'), ('en', 'Hello World'), ('zh', '！这是一个测试。')]
    """
    # First, perform basic segmentation
    segments = split_by_language(text)
    
    # Optionally merge short English segments
    if merge_short:
        segments = merge_short_english_segments(segments, min_en_length)
    
    # Filter out empty segments
    segments = [(lang, text) for lang, text in segments if text.strip()]
    
    return segments
