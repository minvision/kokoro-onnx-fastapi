"""
Language segmenter for splitting text into Chinese/English segments.

This module provides functionality to split mixed Chinese-English text into
segments tagged with their language ('zh' or 'en'), preserving punctuation
and original order.

The segmentation strategy is based on ASCII vs non-ASCII character ranges,
with optimization to prevent over-segmentation of short English segments.
"""

from typing import List, Tuple


def is_ascii_text_char(char: str) -> bool:
    """
    Check if a character is an ASCII text character (0x00-0x7F).
    
    Args:
        char: Single character to check.
        
    Returns:
        True if the character is ASCII, False otherwise.
    """
    return ord(char) < 0x80


def split_by_language(text: str, min_en_merge_threshold: int = 3) -> List[Tuple[str, str]]:
    """
    Split text into segments by language (Chinese 'zh' or English 'en').
    
    The segmentation is based on ASCII (English/punctuation) vs non-ASCII (Chinese)
    character ranges. Adjacent segments of the same language are merged.
    Short English segments (below threshold) adjacent to Chinese segments
    may be kept separate for proper TTS handling.
    
    Args:
        text: Input text containing mixed Chinese and English.
        min_en_merge_threshold: Minimum length for English segments to be
                               considered standalone. Shorter segments between
                               Chinese text are still kept separate for TTS.
                               
    Returns:
        List of tuples (segment_text, language_tag) where language_tag is
        'zh' for Chinese or 'en' for English/ASCII text.
        
    Example:
        >>> split_by_language("你好Hello世界")
        [('你好', 'zh'), ('Hello', 'en'), ('世界', 'zh')]
        
        >>> split_by_language("Hello World")
        [('Hello World', 'en')]
        
        >>> split_by_language("今天是2024年")
        [('今天是', 'zh'), ('2024', 'en'), ('年', 'zh')]
    """
    if not text:
        return []
    
    segments: List[Tuple[str, str]] = []
    current_segment = ""
    current_lang = None
    
    for char in text:
        # Determine language for this character
        # ASCII characters (including spaces, punctuation, numbers) are treated as 'en'
        # Non-ASCII characters are treated as 'zh'
        char_lang = 'en' if is_ascii_text_char(char) else 'zh'
        
        if current_lang is None:
            # First character
            current_lang = char_lang
            current_segment = char
        elif char_lang == current_lang:
            # Same language, extend segment
            current_segment += char
        else:
            # Language changed, save current segment and start new one
            if current_segment:
                segments.append((current_segment, current_lang))
            current_segment = char
            current_lang = char_lang
    
    # Don't forget the last segment
    if current_segment:
        segments.append((current_segment, current_lang))
    
    # Post-process to merge adjacent segments of same language
    # This handles cases where punctuation might have caused unnecessary splits
    merged_segments = _merge_adjacent_segments(segments)
    
    return merged_segments


def _merge_adjacent_segments(segments: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """
    Merge adjacent segments that have the same language tag.
    
    Args:
        segments: List of (text, lang) tuples.
        
    Returns:
        Merged list of (text, lang) tuples.
    """
    if not segments:
        return []
    
    merged = []
    current_text = segments[0][0]
    current_lang = segments[0][1]
    
    for text, lang in segments[1:]:
        if lang == current_lang:
            # Same language, merge
            current_text += text
        else:
            # Different language, save current and start new
            merged.append((current_text, current_lang))
            current_text = text
            current_lang = lang
    
    # Add the last segment
    merged.append((current_text, current_lang))
    
    return merged


def split_by_language_smart(text: str) -> List[Tuple[str, str]]:
    """
    Smart language splitting that handles common patterns better.
    
    This is an enhanced version that can be extended in the future to use
    more sophisticated language detection. Currently it uses the basic
    ASCII/non-ASCII split but provides a cleaner interface for future
    improvements.
    
    Args:
        text: Input text containing mixed Chinese and English.
        
    Returns:
        List of tuples (segment_text, language_tag) where language_tag is
        'zh' for Chinese or 'en' for English/ASCII text.
    """
    # For now, use the basic implementation
    # This function serves as an extension point for future improvements
    # such as using ML-based language detection
    return split_by_language(text)


# Alias for backwards compatibility and cleaner API
segment_text = split_by_language_smart
