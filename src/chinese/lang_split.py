"""
Language splitter for mixed Chinese/English text.
Splits text into segments based on ASCII vs non-ASCII characters.
"""
from typing import List, Tuple


def is_ascii(char: str) -> bool:
    """Check if a character is ASCII (0x00-0x7F)."""
    return ord(char) <= 0x7F


def split_by_language(text: str, min_en_merge_len: int = 3) -> List[Tuple[str, str]]:
    """
    Split text into segments by language (English/ASCII vs Chinese/non-ASCII).
    
    Args:
        text: Input text containing mixed Chinese and English.
        min_en_merge_len: Minimum length for standalone English segments.
                          Shorter English segments will be merged with adjacent Chinese.
    
    Returns:
        List of tuples: [('en'|'zh', segment_text), ...]
        
    Examples:
        >>> split_by_language("你好Hello世界")
        [('zh', '你好'), ('en', 'Hello'), ('zh', '世界')]
        >>> split_by_language("Hello World")
        [('en', 'Hello World')]
        >>> split_by_language("中文测试")
        [('zh', '中文测试')]
    """
    if not text:
        return []
    
    segments: List[Tuple[str, str]] = []
    current_segment = ""
    current_lang = None
    
    for char in text:
        char_is_ascii = is_ascii(char)
        char_lang = 'en' if char_is_ascii else 'zh'
        
        if current_lang is None:
            current_lang = char_lang
            current_segment = char
        elif char_lang == current_lang:
            current_segment += char
        else:
            # Language changed - save current segment and start new one
            if current_segment:
                segments.append((current_lang, current_segment))
            current_lang = char_lang
            current_segment = char
    
    # Don't forget the last segment
    if current_segment:
        segments.append((current_lang, current_segment))
    
    # Post-process: merge short English segments with adjacent Chinese
    if min_en_merge_len > 0:
        segments = _merge_short_english_segments(segments, min_en_merge_len)
    
    return segments


def _merge_short_english_segments(
    segments: List[Tuple[str, str]], 
    min_en_merge_len: int
) -> List[Tuple[str, str]]:
    """
    Merge short English segments with adjacent Chinese segments to reduce
    frequent switching between TTS engines.
    
    Short English segments (e.g., single punctuation, numbers) are often
    better handled by the Chinese TTS if surrounded by Chinese text.
    """
    if not segments:
        return segments
    
    result: List[Tuple[str, str]] = []
    
    for lang, text in segments:
        # Check if this is a short English segment that should be merged
        # Only merge if it's truly short AND the text is mostly non-alphabetic
        # (e.g., punctuation, numbers, whitespace)
        stripped = text.strip()
        should_merge = (
            lang == 'en' and 
            len(stripped) < min_en_merge_len and
            result and 
            result[-1][0] == 'zh' and
            not any(c.isalpha() for c in stripped)
        )
        
        if should_merge:
            # Merge with previous Chinese segment
            prev_lang, prev_text = result.pop()
            result.append((prev_lang, prev_text + text))
        else:
            result.append((lang, text))
    
    # Second pass: merge adjacent segments of same language
    merged: List[Tuple[str, str]] = []
    for lang, text in result:
        if merged and merged[-1][0] == lang:
            prev_lang, prev_text = merged.pop()
            merged.append((prev_lang, prev_text + text))
        else:
            merged.append((lang, text))
    
    return merged
