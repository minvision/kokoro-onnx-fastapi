"""
Language segmentation module for Chinese/English text.

Splits text into consecutive segments of Chinese (non-ASCII) and English (ASCII) characters.
Short English segments can be merged to reduce frequent language switching.
"""

from typing import List, Tuple


def split_text_into_segments(text: str, min_en_merge_len: int = 2) -> List[Tuple[str, str]]:
    """
    Split text into segments by language ('zh' for Chinese/non-ASCII, 'en' for ASCII/English).
    
    Algorithm:
    1. Split text by consecutive ASCII vs non-ASCII characters
    2. Merge short English segments (length < min_en_merge_len) into adjacent Chinese segments
       to reduce frequent TTS model switching
    
    Args:
        text: Input text containing mixed Chinese and English
        min_en_merge_len: Minimum length for an English segment to remain standalone.
                         Shorter English segments are merged with adjacent Chinese.
                         Default is 2.
    
    Returns:
        List of tuples: [('en'|'zh', segment_text), ...]
        Returns empty list if text is empty or whitespace only.
    
    Examples:
        >>> split_text_into_segments("你好world世界")
        [('zh', '你好'), ('en', 'world'), ('zh', '世界')]
        
        >>> split_text_into_segments("Hello 世界")  
        [('en', 'Hello '), ('zh', '世界')]
        
        >>> split_text_into_segments("纯中文文本")
        [('zh', '纯中文文本')]
        
        >>> split_text_into_segments("Pure English text")
        [('en', 'Pure English text')]
    """
    if not text or not text.strip():
        return []
    
    # Split into raw segments by ASCII vs non-ASCII
    raw_segments = _split_by_script(text)
    
    if not raw_segments:
        return []
    
    # Merge short English segments into adjacent Chinese segments
    merged_segments = _merge_short_english(raw_segments, min_en_merge_len)
    
    # Filter out empty segments and consolidate adjacent same-language segments
    final_segments = _consolidate_segments(merged_segments)
    
    return final_segments


def _split_by_script(text: str) -> List[Tuple[str, str]]:
    """
    Split text into segments based on ASCII vs non-ASCII characters.
    
    ASCII characters (including spaces, punctuation) -> 'en'
    Non-ASCII characters (Chinese, etc.) -> 'zh'
    """
    segments = []
    if not text:
        return segments
    
    current_lang = None
    current_text = []
    
    for char in text:
        # Determine if character is ASCII (English/punctuation/space) or non-ASCII (Chinese/other)
        is_ascii = ord(char) < 128
        lang = 'en' if is_ascii else 'zh'
        
        if current_lang is None:
            current_lang = lang
            current_text.append(char)
        elif lang == current_lang:
            current_text.append(char)
        else:
            # Language changed, save current segment and start new
            segment_text = ''.join(current_text)
            if segment_text:
                segments.append((current_lang, segment_text))
            current_lang = lang
            current_text = [char]
    
    # Don't forget the last segment
    if current_text:
        segment_text = ''.join(current_text)
        if segment_text:
            segments.append((current_lang, segment_text))
    
    return segments


def _merge_short_english(segments: List[Tuple[str, str]], min_len: int) -> List[Tuple[str, str]]:
    """
    Merge short English segments (length < min_len) into adjacent Chinese segments.
    
    This reduces frequent switching between TTS models for short English words/phrases
    embedded in Chinese text (e.g., single letters, numbers, short abbreviations).
    
    The Chinese TTS model can often handle these better as part of the Chinese text flow.
    """
    if min_len <= 0:
        return segments
    
    result = []
    
    for lang, text in segments:
        # Strip whitespace to get actual content length for English segments
        stripped_len = len(text.strip()) if lang == 'en' else len(text)
        
        if lang == 'en' and stripped_len < min_len:
            # Short English segment - merge with previous or mark for next merge
            if result and result[-1][0] == 'zh':
                # Append to previous Chinese segment
                prev_lang, prev_text = result[-1]
                result[-1] = (prev_lang, prev_text + text)
            else:
                # No previous Chinese segment, keep as potential merge target
                # but mark it as 'zh' so it can be merged with next Chinese
                result.append(('zh', text))
        else:
            result.append((lang, text))
    
    return result


def _consolidate_segments(segments: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """
    Consolidate adjacent segments of the same language and filter out empty segments.
    """
    if not segments:
        return []
    
    consolidated = []
    
    for lang, text in segments:
        if not text:  # Skip empty segments
            continue
            
        if consolidated and consolidated[-1][0] == lang:
            # Same language as previous, merge
            prev_lang, prev_text = consolidated[-1]
            consolidated[-1] = (prev_lang, prev_text + text)
        else:
            consolidated.append((lang, text))
    
    return consolidated


def is_primarily_chinese(text: str) -> bool:
    """
    Check if text is primarily Chinese (more than 50% non-ASCII characters).
    
    Useful for determining default voice selection.
    """
    if not text:
        return False
    
    non_ascii_count = sum(1 for char in text if ord(char) >= 128)
    return non_ascii_count > len(text) / 2


def is_primarily_english(text: str) -> bool:
    """
    Check if text is primarily English (more than 50% ASCII letters).
    
    Useful for determining default voice selection.
    """
    if not text:
        return False
    
    ascii_letter_count = sum(1 for char in text if char.isascii() and char.isalpha())
    return ascii_letter_count > len(text) / 2
