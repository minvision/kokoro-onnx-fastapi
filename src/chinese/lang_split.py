"""
Text segmentation module for splitting mixed Chinese/English text.

Splits text into segments of consecutive ASCII (English) and non-ASCII (Chinese) characters.
Returns a list of tuples: [('en'|'zh', text), ...]
"""

from typing import List, Tuple


def is_ascii(char: str) -> bool:
    """Check if a character is ASCII (0x00-0x7F)."""
    return ord(char) <= 0x7F


def split_by_language(
    text: str,
    min_segment_length: int = 1
) -> List[Tuple[str, str]]:
    """
    Split text into segments by language (ASCII vs non-ASCII).
    
    Args:
        text: The input text to split.
        min_segment_length: Minimum length for a segment to stand alone.
                           Shorter segments may be merged with adjacent segments
                           of the same type to reduce fragmentation.
    
    Returns:
        List of tuples (language, text) where language is 'en' for ASCII text
        and 'zh' for non-ASCII text.
    
    Examples:
        >>> split_by_language("Hello世界")
        [('en', 'Hello'), ('zh', '世界')]
        >>> split_by_language("你好World你好")
        [('zh', '你好'), ('en', 'World'), ('zh', '你好')]
    """
    if not text:
        return []
    
    segments: List[Tuple[str, str]] = []
    current_text = ""
    current_is_ascii = None
    
    for char in text:
        char_is_ascii = is_ascii(char)
        
        # Whitespace and common punctuation should follow the current segment's language
        # This prevents fragmentation on spaces/punctuation between same-language words
        # Note: This is a basic set of ASCII punctuation. Chinese punctuation (。，！？等)
        # is non-ASCII and will be handled as part of Chinese segments.
        if char.isspace() or char in '.,!?;:\'"-()[]{}':
            current_text += char
            continue
        
        if current_is_ascii is None:
            current_is_ascii = char_is_ascii
            current_text = char
        elif char_is_ascii == current_is_ascii:
            current_text += char
        else:
            # Language boundary detected
            if current_text.strip():  # Only add non-empty segments
                lang = 'en' if current_is_ascii else 'zh'
                segments.append((lang, current_text))
            current_text = char
            current_is_ascii = char_is_ascii
    
    # Add the last segment
    if current_text.strip():
        lang = 'en' if current_is_ascii else 'zh'
        segments.append((lang, current_text))
    
    # Post-process: merge small segments with the same language as neighbors
    if min_segment_length > 1 and len(segments) > 1:
        segments = _merge_small_segments(segments, min_segment_length)
    
    return segments


def _merge_small_segments(
    segments: List[Tuple[str, str]],
    min_length: int
) -> List[Tuple[str, str]]:
    """
    Merge small segments with adjacent segments of the same language.
    
    This helps reduce over-fragmentation when there are short isolated
    characters or words.
    """
    if not segments:
        return segments
    
    result = []
    i = 0
    
    while i < len(segments):
        lang, text = segments[i]
        
        # If segment is short and not the last one
        if len(text.strip()) < min_length and i < len(segments) - 1:
            # Look ahead to see if next segment has same language
            next_lang, next_text = segments[i + 1]
            if next_lang == lang:
                # Merge with next segment
                segments[i + 1] = (lang, text + next_text)
                i += 1
                continue
        
        # Check if we can merge with the previous result segment
        if result and result[-1][0] == lang:
            prev_lang, prev_text = result.pop()
            result.append((lang, prev_text + text))
        else:
            result.append((lang, text))
        
        i += 1
    
    return result


def get_primary_language(text: str) -> str:
    """
    Determine the primary language of the text based on character count.
    
    Args:
        text: Input text to analyze.
    
    Returns:
        'en' if primarily ASCII, 'zh' if primarily non-ASCII.
    """
    if not text:
        return 'zh'  # Default to Chinese
    
    ascii_count = sum(1 for char in text if is_ascii(char) and not char.isspace())
    non_ascii_count = sum(1 for char in text if not is_ascii(char))
    
    return 'en' if ascii_count > non_ascii_count else 'zh'
