"""
Tests for mixed Chinese/English TTS streaming.

This module contains tests for:
1. Language splitting (lang_split.py)
2. Mixed stream generation (mixed_stream.py)
3. End-to-end RTP/UDP streaming with mock UDP receiver

Note: These tests are designed to run without the actual TTS models
by using mocks where appropriate. Integration tests that require
actual models should be run manually with the test fixtures.
"""

import pytest
import asyncio
import sys
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import AsyncGenerator, Tuple
import numpy as np

# Add src/chinese to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'chinese'))


class TestLangSplit:
    """Tests for the language splitting module."""
    
    def test_import_lang_split(self):
        """Test that lang_split module can be imported."""
        from lang_split import split_by_language, is_ascii, get_primary_language
        assert callable(split_by_language)
        assert callable(is_ascii)
        assert callable(get_primary_language)
    
    def test_is_ascii(self):
        """Test ASCII character detection."""
        from lang_split import is_ascii
        
        # ASCII characters
        assert is_ascii('a') == True
        assert is_ascii('Z') == True
        assert is_ascii('0') == True
        assert is_ascii(' ') == True
        assert is_ascii('!') == True
        
        # Non-ASCII characters
        assert is_ascii('中') == False
        assert is_ascii('文') == False
        assert is_ascii('日') == False
        assert is_ascii('한') == False
        assert is_ascii('é') == False
    
    def test_split_pure_chinese(self):
        """Test splitting pure Chinese text."""
        from lang_split import split_by_language
        
        result = split_by_language("你好世界")
        assert len(result) == 1
        assert result[0][0] == 'zh'
        assert result[0][1] == "你好世界"
    
    def test_split_pure_english(self):
        """Test splitting pure English text."""
        from lang_split import split_by_language
        
        result = split_by_language("Hello World")
        assert len(result) == 1
        assert result[0][0] == 'en'
        assert "Hello World" in result[0][1]
    
    def test_split_mixed_text(self):
        """Test splitting mixed Chinese/English text."""
        from lang_split import split_by_language
        
        result = split_by_language("Hello世界")
        assert len(result) == 2
        assert result[0][0] == 'en'
        assert result[1][0] == 'zh'
    
    def test_split_mixed_text_multiple_segments(self):
        """Test splitting text with multiple language switches."""
        from lang_split import split_by_language
        
        result = split_by_language("你好World你好")
        assert len(result) == 3
        assert result[0][0] == 'zh'
        assert result[1][0] == 'en'
        assert result[2][0] == 'zh'
    
    def test_split_empty_text(self):
        """Test splitting empty text."""
        from lang_split import split_by_language
        
        result = split_by_language("")
        assert result == []
    
    def test_split_whitespace_only(self):
        """Test splitting whitespace-only text."""
        from lang_split import split_by_language
        
        result = split_by_language("   ")
        assert result == []
    
    def test_get_primary_language_chinese(self):
        """Test primary language detection for Chinese-dominant text."""
        from lang_split import get_primary_language
        
        assert get_primary_language("你好世界Hello") == 'zh'
        assert get_primary_language("中文测试") == 'zh'
    
    def test_get_primary_language_english(self):
        """Test primary language detection for English-dominant text."""
        from lang_split import get_primary_language
        
        assert get_primary_language("Hello World 你") == 'en'
        assert get_primary_language("English text only") == 'en'
    
    def test_get_primary_language_empty(self):
        """Test primary language detection for empty text."""
        from lang_split import get_primary_language
        
        # Default to Chinese for empty text
        assert get_primary_language("") == 'zh'


class TestMixedStream:
    """Tests for the mixed stream module."""
    
    def test_import_mixed_stream(self):
        """Test that mixed_stream module can be imported."""
        from mixed_stream import create_mixed_stream, detect_language_segments
        assert callable(create_mixed_stream)
        assert callable(detect_language_segments)
    
    def test_detect_language_segments(self):
        """Test the utility function for detecting language segments."""
        from mixed_stream import detect_language_segments
        
        segments = detect_language_segments("Hello世界")
        assert len(segments) == 2
    
    @pytest.mark.asyncio
    async def test_create_mixed_stream_with_mock_models(self):
        """Test create_mixed_stream with mock models."""
        from mixed_stream import create_mixed_stream
        
        # Create mock models
        mock_kokoro_model = MagicMock()
        mock_g2p_converter = MagicMock(return_value=("phonemes", None))
        
        # Create a mock async generator for create_stream
        async def mock_stream_gen():
            yield np.zeros(100, dtype=np.float32), 24000
        
        mock_kokoro_model.create_stream = MagicMock(return_value=mock_stream_gen())
        
        # Test with Chinese-only text (no need for English model)
        with patch('mixed_stream.is_english_model_ready', return_value=False):
            stream = create_mixed_stream(
                text="你好",
                kokoro_model=mock_kokoro_model,
                g2p_converter=mock_g2p_converter,
                voice="zf_001",
                speed=1.0
            )
            
            chunks = []
            async for chunk, sr in stream:
                chunks.append((chunk, sr))
            
            assert len(chunks) >= 1
            mock_g2p_converter.assert_called()
    
    @pytest.mark.asyncio
    async def test_create_mixed_stream_raises_without_model(self):
        """Test that create_mixed_stream raises error without model."""
        from mixed_stream import create_mixed_stream
        
        with pytest.raises(RuntimeError, match="Chinese model not initialized"):
            stream = create_mixed_stream(
                text="Hello",
                kokoro_model=None,
                g2p_converter=Mock(),
                voice="zf_001",
                speed=1.0
            )
            # Need to actually iterate to trigger the error
            async for _ in stream:
                pass
    
    @pytest.mark.asyncio
    async def test_create_mixed_stream_raises_without_g2p(self):
        """Test that create_mixed_stream raises error without g2p."""
        from mixed_stream import create_mixed_stream
        
        with pytest.raises(RuntimeError, match="Chinese G2P converter not initialized"):
            stream = create_mixed_stream(
                text="Hello",
                kokoro_model=Mock(),
                g2p_converter=None,
                voice="zf_001",
                speed=1.0
            )
            async for _ in stream:
                pass


class TestEnglishTTS:
    """Tests for the English TTS adapter module."""
    
    def test_import_english_tts(self):
        """Test that english_tts module can be imported."""
        from english_tts import (
            initialize_english_model,
            is_english_model_ready,
            get_default_english_voice,
            ENGLISH_DEPENDENCIES
        )
        assert callable(initialize_english_model)
        assert callable(is_english_model_ready)
        assert callable(get_default_english_voice)
        assert isinstance(ENGLISH_DEPENDENCIES, dict)
    
    def test_english_dependencies_defined(self):
        """Test that English model dependencies are properly defined."""
        from english_tts import ENGLISH_DEPENDENCIES
        
        assert "kokoro-v1.0.onnx" in ENGLISH_DEPENDENCIES
        assert "voices-v1.0.bin" in ENGLISH_DEPENDENCIES
    
    def test_default_english_voice(self):
        """Test default English voice."""
        from english_tts import get_default_english_voice
        
        voice = get_default_english_voice()
        assert isinstance(voice, str)
        assert len(voice) > 0


class TestUDPStreaming:
    """Tests for UDP streaming functionality."""
    
    @pytest.mark.asyncio
    async def test_udp_loopback_receives_data(self):
        """Test that UDP loopback receives data correctly."""
        import socket
        
        # Create a simple UDP receiver
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        receiver.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        receiver.bind(('127.0.0.1', 0))  # Let OS assign port
        receiver.settimeout(2.0)
        
        port = receiver.getsockname()[1]
        
        # Create a sender
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        try:
            # Send test data
            test_data = b"test_rtp_packet_data"
            sender.sendto(test_data, ('127.0.0.1', port))
            
            # Receive and verify
            data, addr = receiver.recvfrom(1024)
            assert data == test_data
            
        finally:
            sender.close()
            receiver.close()
    
    @pytest.mark.asyncio
    async def test_stream_rtp_from_asyncgen_import(self):
        """Test that stream_rtp_from_asyncgen can be imported."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
        
        from utils.stream_rtp_streaming import stream_rtp_from_asyncgen
        assert callable(stream_rtp_from_asyncgen)
    
    @pytest.mark.asyncio
    async def test_stream_rtp_with_mock_generator(self):
        """Test stream_rtp_from_asyncgen with a mock audio generator."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
        
        from utils.stream_rtp_streaming import stream_rtp_from_asyncgen
        import socket
        
        # Create UDP receiver
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        receiver.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        receiver.bind(('127.0.0.1', 0))
        receiver.settimeout(5.0)
        port = receiver.getsockname()[1]
        
        received_packets = []
        
        # Start receiver in background
        async def receive_loop():
            try:
                while True:
                    try:
                        data, _ = receiver.recvfrom(4096)
                        received_packets.append(data)
                    except socket.timeout:
                        break
            except Exception:
                pass
        
        # Create mock audio generator
        async def mock_audio_gen():
            for i in range(3):
                # Generate small audio chunk
                samples = np.sin(np.linspace(0, 2*np.pi, 160)).astype(np.float32)
                yield samples, 8000
        
        try:
            # Start receiver and sender concurrently
            recv_task = asyncio.create_task(receive_loop())
            
            result = await stream_rtp_from_asyncgen(
                host='127.0.0.1',
                port=port,
                async_gen=mock_audio_gen(),
                realtime=False,  # Don't wait between packets for test speed
                chunk_ms=20,
                target_sr=8000,
                codec='l16'
            )
            
            # Give receiver time to get all packets
            await asyncio.sleep(0.5)
            recv_task.cancel()
            try:
                await recv_task
            except asyncio.CancelledError:
                pass
            
            # Verify result
            assert isinstance(result, dict)
            assert 'final_seq' in result
            assert 'final_timestamp' in result
            assert 'ssrc' in result
            
            # Should have received at least some packets
            assert len(received_packets) > 0
            
        finally:
            receiver.close()


# Integration test fixtures (requires actual models)
class TestIntegration:
    """Integration tests that require actual TTS models.
    
    These tests are marked with pytest.mark.integration and are skipped
    by default. Run with: pytest -m integration
    """
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_mixed_stream_pipeline(self):
        """Full integration test with actual models.
        
        This test requires:
        - Chinese Kokoro model files in src/chinese/models/
        - English Kokoro model files in src/chinese/models/
        """
        pytest.skip("Integration test - requires actual model files")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
