"""
Tests for mixed TTS functionality.
Tests language segmentation, audio utilities, and socket streaming.
"""

import pytest
import asyncio
import socket
import sys
import os

# Add src/chinese to path for imports
src_chinese_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'chinese')
if src_chinese_path not in sys.path:
    sys.path.insert(0, src_chinese_path)

# Import modules directly (not as relative imports)
import utils as utils_module
import stream_sender as stream_sender_module

# Get functions from utils
segment_by_language = utils_module.segment_by_language
merge_short_segments = utils_module.merge_short_segments
clean_segment_text = utils_module.clean_segment_text
is_ascii_char = utils_module.is_ascii_char
ensure_mono = utils_module.ensure_mono
resample_linear = utils_module.resample_linear
float_to_int16_bytes = utils_module.float_to_int16_bytes
int16_bytes_to_float = utils_module.int16_bytes_to_float
concatenate_audio = utils_module.concatenate_audio
validate_sample_rate = utils_module.validate_sample_rate
estimate_audio_duration = utils_module.estimate_audio_duration

# Get classes from stream_sender
StreamSender = stream_sender_module.StreamSender
Protocol = stream_sender_module.Protocol

import numpy as np


def detect_language_mix(text: str) -> dict:
    """
    Analyze text for language composition.
    Reimplemented here to avoid circular import issues.
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


class TestLanguageSegmentation:
    """Tests for language segmentation functions."""
    
    def test_is_ascii_char(self):
        """Test ASCII character detection."""
        assert is_ascii_char('a') == True
        assert is_ascii_char('Z') == True
        assert is_ascii_char('5') == True
        assert is_ascii_char(' ') == True
        assert is_ascii_char('.') == True
        assert is_ascii_char('你') == False
        assert is_ascii_char('好') == False
        assert is_ascii_char('世') == False
    
    def test_segment_pure_chinese(self):
        """Test segmentation of pure Chinese text."""
        text = "你好世界"
        segments = segment_by_language(text)
        
        assert len(segments) == 1
        assert segments[0][0] == "你好世界"
        assert segments[0][1] == "zh"
    
    def test_segment_pure_english(self):
        """Test segmentation of pure English text."""
        text = "Hello world"
        segments = segment_by_language(text)
        
        assert len(segments) == 1
        assert segments[0][0] == "Hello world"
        assert segments[0][1] == "en"
    
    def test_segment_mixed_text(self):
        """Test segmentation of mixed Chinese-English text."""
        text = "你好，hello world，世界"
        segments = segment_by_language(text)
        
        # Should have multiple segments alternating between zh and en
        assert len(segments) >= 3
        
        # First segment should be Chinese
        assert segments[0][1] == "zh"
        
        # Check that both languages are present
        langs = [s[1] for s in segments]
        assert "zh" in langs
        assert "en" in langs
    
    def test_segment_empty_text(self):
        """Test segmentation of empty text."""
        segments = segment_by_language("")
        assert segments == []
    
    def test_segment_only_spaces(self):
        """Test segmentation of text with only spaces."""
        segments = segment_by_language("   ")
        assert segments == []
    
    def test_segment_with_numbers(self):
        """Test segmentation with numbers (should be English/ASCII)."""
        text = "价格是100元"
        segments = segment_by_language(text)
        
        # Numbers should be grouped with English
        found_number = any("100" in s[0] for s in segments)
        assert found_number
    
    def test_merge_short_segments(self):
        """Test merging of short segments."""
        segments = [
            ("你好", "zh"),
            (".", "en"),  # Short segment
            ("世界", "zh")
        ]
        
        merged = merge_short_segments(segments, min_length=2)
        
        # Short segment should be merged
        assert len(merged) <= len(segments)
    
    def test_clean_segment_text(self):
        """Test text cleaning."""
        text = "  hello   world  \n\t test  "
        cleaned = clean_segment_text(text)
        
        assert cleaned == "hello world test"


class TestDetectLanguageMix:
    """Tests for language detection function."""
    
    def test_detect_pure_chinese(self):
        """Test detection of pure Chinese text."""
        result = detect_language_mix("你好世界")
        
        assert result['has_chinese'] == True
        assert result['has_english'] == False
        assert result['is_mixed'] == False
        assert result['chinese_ratio'] > 0.9
    
    def test_detect_pure_english(self):
        """Test detection of pure English text."""
        result = detect_language_mix("Hello world")
        
        assert result['has_chinese'] == False
        assert result['has_english'] == True
        assert result['is_mixed'] == False
        assert result['english_ratio'] > 0.9
    
    def test_detect_mixed(self):
        """Test detection of mixed text."""
        result = detect_language_mix("你好 hello 世界 world")
        
        assert result['has_chinese'] == True
        assert result['has_english'] == True
        assert result['is_mixed'] == True
        assert result['segment_count'] >= 2


class TestAudioUtils:
    """Tests for audio utility functions."""
    
    def test_ensure_mono_already_mono(self):
        """Test ensure_mono with already mono audio."""
        samples = np.array([0.1, 0.2, 0.3, 0.4])
        result = ensure_mono(samples)
        
        np.testing.assert_array_equal(result, samples)
    
    def test_ensure_mono_stereo(self):
        """Test ensure_mono with stereo audio."""
        samples = np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]])
        result = ensure_mono(samples)
        
        assert result.ndim == 1
        assert len(result) == 3
        # Should be average of channels
        np.testing.assert_array_almost_equal(result, [0.15, 0.35, 0.55])
    
    def test_resample_same_rate(self):
        """Test resample with same input/output rate."""
        samples = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        result = resample_linear(samples, 24000, 24000)
        
        np.testing.assert_array_equal(result, samples)
    
    def test_resample_downsample(self):
        """Test resampling to lower rate."""
        samples = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        result = resample_linear(samples, 48000, 24000)
        
        # Should have approximately half the samples
        assert len(result) == 2
    
    def test_resample_upsample(self):
        """Test resampling to higher rate."""
        samples = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        result = resample_linear(samples, 24000, 48000)
        
        # Should have approximately double the samples
        assert len(result) == 8
    
    def test_float_to_int16_bytes(self):
        """Test conversion from float to int16 bytes."""
        samples = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
        result = float_to_int16_bytes(samples)
        
        # Should produce 2 bytes per sample
        assert len(result) == 10
        
        # Check that it's valid PCM data
        int16_arr = np.frombuffer(result, dtype=np.int16)
        assert len(int16_arr) == 5
    
    def test_int16_bytes_to_float(self):
        """Test conversion from int16 bytes to float."""
        # Create some PCM data
        original = np.array([0.0, 0.5, -0.5], dtype=np.float32)
        pcm_bytes = float_to_int16_bytes(original)
        
        # Convert back
        result = int16_bytes_to_float(pcm_bytes)
        
        # Should be close to original (with some quantization error)
        np.testing.assert_array_almost_equal(result, original, decimal=3)
    
    def test_concatenate_audio_single(self):
        """Test concatenating a single audio part."""
        samples = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        parts = [(samples, 24000)]
        
        result, sr = concatenate_audio(parts, target_sr=24000)
        
        np.testing.assert_array_equal(result, samples)
        assert sr == 24000
    
    def test_concatenate_audio_multiple(self):
        """Test concatenating multiple audio parts."""
        part1 = np.array([0.1, 0.2], dtype=np.float32)
        part2 = np.array([0.3, 0.4], dtype=np.float32)
        parts = [(part1, 24000), (part2, 24000)]
        
        result, sr = concatenate_audio(parts, target_sr=24000)
        
        assert len(result) == 4
        assert sr == 24000
    
    def test_validate_sample_rate(self):
        """Test sample rate validation."""
        assert validate_sample_rate(24000) == True
        assert validate_sample_rate(48000) == True
        assert validate_sample_rate(8000) == True
        assert validate_sample_rate(12345) == False
    
    def test_estimate_audio_duration(self):
        """Test audio duration estimation."""
        # 24000 samples at 24000 Hz = 1 second
        samples = np.zeros(24000)
        duration = estimate_audio_duration(samples, 24000)
        
        assert duration == 1.0


class TestStreamSender:
    """Tests for StreamSender class."""
    
    @pytest.mark.asyncio
    async def test_sender_init(self):
        """Test StreamSender initialization."""
        sender = StreamSender("127.0.0.1", 5200, Protocol.UDP)
        
        assert sender.host == "127.0.0.1"
        assert sender.port == 5200
        assert sender.protocol == Protocol.UDP
        assert sender.is_connected == False
    
    @pytest.mark.asyncio
    async def test_sender_protocol_string(self):
        """Test StreamSender with string protocol."""
        sender = StreamSender("127.0.0.1", 5200, "tcp")
        
        assert sender.protocol == Protocol.TCP
    
    @pytest.mark.asyncio
    async def test_udp_sender_connect(self):
        """Test UDP sender connection."""
        sender = StreamSender("127.0.0.1", 5200, Protocol.UDP)
        
        result = await sender.connect()
        
        # UDP connection should succeed (it's connectionless)
        assert result == True
        assert sender.is_connected == True
        
        await sender.close()
        assert sender.is_connected == False
    
    @pytest.mark.asyncio
    async def test_udp_send_to_loopback(self):
        """Test UDP sending to loopback receiver."""
        # Start a UDP receiver
        recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        recv_sock.bind(("127.0.0.1", 0))  # Bind to random port
        recv_port = recv_sock.getsockname()[1]
        recv_sock.settimeout(2.0)
        
        # Create sender
        sender = StreamSender("127.0.0.1", recv_port, Protocol.UDP)
        await sender.connect()
        
        # Send data
        test_data = b"test audio data"
        result = await sender.send(test_data)
        
        assert result == True
        
        # Receive and verify
        try:
            received, addr = recv_sock.recvfrom(1024)
            assert received == test_data
        finally:
            recv_sock.close()
            await sender.close()
    
    @pytest.mark.asyncio
    async def test_sender_context_manager(self):
        """Test StreamSender as async context manager."""
        async with StreamSender("127.0.0.1", 5200, Protocol.UDP) as sender:
            assert sender.is_connected == True
        
        assert sender.is_connected == False


class TestIntegration:
    """Integration tests for the mixed TTS system."""
    
    @pytest.mark.asyncio
    async def test_socket_streaming_simulation(self):
        """Test simulated socket streaming workflow."""
        # Create UDP receiver
        recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        recv_sock.bind(("127.0.0.1", 0))
        recv_port = recv_sock.getsockname()[1]
        recv_sock.settimeout(2.0)
        
        received_data = []
        
        # Create sender
        async with StreamSender("127.0.0.1", recv_port, Protocol.UDP) as sender:
            # Simulate sending audio chunks
            for i in range(5):
                # Create fake audio chunk
                samples = np.random.random(1000).astype(np.float32) * 2 - 1
                pcm_bytes = float_to_int16_bytes(samples)
                
                await sender.send(pcm_bytes)
                
                # Small delay to allow socket processing
                await asyncio.sleep(0.01)
        
        # Receive all data
        recv_sock.setblocking(False)
        while True:
            try:
                data, _ = recv_sock.recvfrom(65536)
                received_data.append(data)
            except BlockingIOError:
                break
        
        recv_sock.close()
        
        # Verify data was received
        assert len(received_data) >= 1
        total_bytes = sum(len(d) for d in received_data)
        assert total_bytes > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
