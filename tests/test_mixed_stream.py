"""
Integration tests for mixed language (Chinese/English) TTS stream.

These tests use mocked Kokoro models to avoid loading large model files.
For full E2E testing with real models, see the manual testing instructions
in the repository README.
"""

import sys
import pathlib
import pytest
from unittest.mock import Mock, patch
from typing import AsyncGenerator, Tuple

import numpy as np

# Add src to path
SRC_DIR = str(pathlib.Path(__file__).resolve().parents[1] / "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


class TestLangSplit:
    """Tests for language segmentation module."""
    
    def test_pure_chinese(self):
        """Test pure Chinese text returns single segment."""
        from chinese.lang_split import split_text_into_segments
        
        result = split_text_into_segments("你好世界")
        assert len(result) == 1
        assert result[0][0] == 'zh'
        assert result[0][1] == "你好世界"
    
    def test_pure_english(self):
        """Test pure English text returns single segment."""
        from chinese.lang_split import split_text_into_segments
        
        result = split_text_into_segments("Hello World")
        assert len(result) == 1
        assert result[0][0] == 'en'
        assert result[0][1] == "Hello World"
    
    def test_mixed_chinese_english(self):
        """Test mixed Chinese and English text."""
        from chinese.lang_split import split_text_into_segments
        
        result = split_text_into_segments("你好Hello世界World")
        assert len(result) == 4
        assert result[0] == ('zh', '你好')
        assert result[1] == ('en', 'Hello')
        assert result[2] == ('zh', '世界')
        assert result[3] == ('en', 'World')
    
    def test_short_english_merge(self):
        """Test that short English segments are merged into Chinese."""
        from chinese.lang_split import split_text_into_segments
        
        # Single letter 'A' should be merged with adjacent Chinese
        result = split_text_into_segments("中文A中文", min_en_merge_len=2)
        # 'A' is shorter than 2, should be merged
        assert len(result) == 1
        assert result[0][0] == 'zh'
        assert 'A' in result[0][1]
    
    def test_empty_text(self):
        """Test empty text returns empty list."""
        from chinese.lang_split import split_text_into_segments
        
        assert split_text_into_segments("") == []
        assert split_text_into_segments("   ") == []
        assert split_text_into_segments(None) == []
    
    def test_english_with_punctuation(self):
        """Test English text with punctuation and spaces."""
        from chinese.lang_split import split_text_into_segments
        
        result = split_text_into_segments("Hello, World!")
        assert len(result) == 1
        assert result[0][0] == 'en'
        assert result[0][1] == "Hello, World!"
    
    def test_primarily_chinese(self):
        """Test is_primarily_chinese function."""
        from chinese.lang_split import is_primarily_chinese
        
        assert is_primarily_chinese("中文文本") == True
        assert is_primarily_chinese("English text") == False
        assert is_primarily_chinese("中中中混合") == True  # All 5 characters are Chinese (non-ASCII)
        assert is_primarily_chinese("") == False
    
    def test_primarily_english(self):
        """Test is_primarily_english function."""
        from chinese.lang_split import is_primarily_english
        
        assert is_primarily_english("English text") == True
        assert is_primarily_english("中文文本") == False
        assert is_primarily_english("") == False


class TestMixedStream:
    """Tests for mixed language TTS stream."""
    
    @pytest.fixture
    def mock_kokoro_chinese(self):
        """Create a mock Chinese Kokoro model."""
        mock = Mock()
        
        async def mock_create_stream(phonemes, voice=None, speed=1.0, is_phonemes=True):
            # Yield a simple sine wave as fake audio
            sr = 24000
            duration = 0.1  # 100ms
            t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
            audio = np.sin(2 * np.pi * 440 * t)  # 440 Hz sine wave
            yield (audio, sr)
        
        mock.create_stream = mock_create_stream
        return mock
    
    @pytest.fixture
    def mock_g2p_chinese(self):
        """Create a mock Chinese G2P converter."""
        def mock_g2p(text):
            # Return dummy phonemes
            return f"phonemes_for_{text[:10]}", None
        
        mock = Mock(side_effect=mock_g2p)
        return mock
    
    @pytest.mark.asyncio
    async def test_pure_chinese_stream(self, mock_kokoro_chinese, mock_g2p_chinese):
        """Test streaming pure Chinese text."""
        from chinese.mixed_stream import create_mixed_stream
        
        chunks = []
        async for chunk in create_mixed_stream(
            text="你好世界",
            kokoro_chinese=mock_kokoro_chinese,
            g2p_chinese=mock_g2p_chinese,
            voice="zf_001"
        ):
            chunks.append(chunk)
        
        assert len(chunks) >= 1
        for audio, sr in chunks:
            assert isinstance(audio, np.ndarray)
            assert sr == 24000
    
    @pytest.mark.asyncio
    async def test_empty_text(self, mock_kokoro_chinese, mock_g2p_chinese):
        """Test streaming empty text returns no chunks."""
        from chinese.mixed_stream import create_mixed_stream
        
        chunks = []
        async for chunk in create_mixed_stream(
            text="",
            kokoro_chinese=mock_kokoro_chinese,
            g2p_chinese=mock_g2p_chinese
        ):
            chunks.append(chunk)
        
        assert len(chunks) == 0
    
    @pytest.mark.asyncio
    async def test_mixed_text_without_english_model(self, mock_kokoro_chinese, mock_g2p_chinese):
        """Test mixed text falls back to Chinese when English model unavailable."""
        from chinese.mixed_stream import create_mixed_stream
        
        # Patch English model to be unavailable
        with patch('chinese.mixed_stream.is_english_model_available', return_value=False):
            chunks = []
            async for chunk in create_mixed_stream(
                text="你好Hello世界",
                kokoro_chinese=mock_kokoro_chinese,
                g2p_chinese=mock_g2p_chinese
            ):
                chunks.append(chunk)
            
            # Should still produce output using Chinese model
            assert len(chunks) >= 1
    
    def test_check_availability(self):
        """Test availability check function."""
        from chinese.mixed_stream import check_mixed_stream_availability
        
        with patch('chinese.mixed_stream.is_english_model_available', return_value=True):
            result = check_mixed_stream_availability()
            assert result['chinese_available'] == True
            assert result['english_available'] == True
        
        with patch('chinese.mixed_stream.is_english_model_available', return_value=False):
            result = check_mixed_stream_availability()
            assert result['chinese_available'] == True
            assert result['english_available'] == False


class TestEnglishTTS:
    """Tests for English TTS adapter."""
    
    def test_set_english_model(self):
        """Test manually setting English model."""
        from chinese.english_tts import set_english_model, is_english_model_available
        
        mock_model = Mock()
        mock_g2p = Mock()
        
        set_english_model(mock_model, mock_g2p)
        
        # After setting, model should be available
        assert is_english_model_available() == True
    
    @pytest.mark.asyncio
    async def test_english_stream_with_mock(self):
        """Test English stream with mock model."""
        from chinese.english_tts import create_english_stream, set_english_model
        
        # Create mock model with create_stream
        mock_model = Mock()
        
        async def mock_stream(phonemes, voice=None, speed=1.0, is_phonemes=True):
            sr = 24000
            t = np.linspace(0, 0.1, int(sr * 0.1), dtype=np.float32)
            audio = np.sin(2 * np.pi * 440 * t)
            yield (audio, sr)
        
        mock_model.create_stream = mock_stream
        mock_g2p = Mock(return_value=("phonemes", None))
        
        set_english_model(mock_model, mock_g2p)
        
        chunks = []
        async for chunk in create_english_stream("Hello World"):
            chunks.append(chunk)
        
        assert len(chunks) >= 1
        for audio, sr in chunks:
            assert isinstance(audio, np.ndarray)
            assert sr == 24000


class TestStreamRTPIntegration:
    """Integration tests for RTP streaming (requires mocking)."""
    
    @pytest.mark.asyncio
    async def test_stream_rtp_basic(self):
        """Test basic RTP streaming functionality."""
        from utils.stream_rtp_streaming import stream_rtp_from_asyncgen
        
        async def simple_audio_gen():
            sr = 8000
            t = np.linspace(0, 0.1, int(sr * 0.1), dtype=np.float32)
            audio = np.sin(2 * np.pi * 440 * t)
            yield (audio, sr)
        
        # Use localhost with a random high port (won't actually send)
        # This tests the RTP packet generation logic
        with patch('asyncio.get_running_loop') as mock_loop:
            mock_transport = Mock()
            mock_transport.sendto = Mock()
            mock_transport.get_extra_info = Mock(return_value=('127.0.0.1', 12345))
            mock_transport.close = Mock()
            
            async def mock_endpoint(*args, **kwargs):
                return (mock_transport, None)
            
            mock_loop.return_value.create_datagram_endpoint = mock_endpoint
            
            result = await stream_rtp_from_asyncgen(
                host='127.0.0.1',
                port=9999,
                async_gen=simple_audio_gen(),
                realtime=False,  # Don't wait between packets
                chunk_ms=20,
                target_sr=8000,
                codec='pcmu'
            )
            
            assert 'final_seq' in result
            assert 'final_timestamp' in result
            assert 'ssrc' in result


# Run tests if executed directly
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
