'''
音频文件缓存相关功能
'''
import os

def check_audio_cache(filename: str, audio_output_dir: str):
    """
    检查指定的音频文件是否已存在于缓存（输出目录）中。

    Args:
        filename: 文件名 (不含后缀和路径)。
        audio_output_dir: 音频文件的输出/缓存目录。

    Returns:
        如果文件存在，则返回文件的完整路径，否则返回 None。
    """
    if not filename:
        return None
    
    # 构建预期的 .wav 文件路径
    # 移除可能存在的后缀，并确保是 .wav
    base_filename, _ = os.path.splitext(filename)
    expected_filepath = os.path.join(audio_output_dir, f"{base_filename}.wav")

    if os.path.exists(expected_filepath):
        return expected_filepath
    return None 