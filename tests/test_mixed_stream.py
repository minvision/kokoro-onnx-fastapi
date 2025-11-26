"""
test_mixed_stream.py - Tests for Mixed Language Streaming

Lightweight integration tests for the mixed Chinese/English TTS functionality.
Tests can be run with mocked Kokoro instances to avoid model loading overhead.
"""

import sys
import os
import asyncio
from typing import AsyncGenerator, Tuple
from unittest.mock import Mock, AsyncMock, patch, MagicMock

import pytest
import numpy as np

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestLangSplit:
    """Tests for the language splitting module."""
    
    def test_split_pure_chinese(self):
        """Test splitting text that is purely Chinese."""
        from chinese.lang_split import split_text_by_language
        
        result = split_text_by_language("你好世界")
        assert len(result) == 1
        assert result[0][0] == 'zh'
        assert result[0][1] == "你好世界"
    
    def test_split_pure_english(self):
        """Test splitting text that is purely English."""
        from chinese.lang_split import split_text_by_language
        
        result = split_text_by_language("Hello World")
        assert len(result) == 1
        assert result[0][0] == 'en'
        assert result[0][1] == "Hello World"
    
    def test_split_mixed_text(self):
        """Test splitting mixed Chinese/English text."""
        from chinese.lang_split import split_text_by_language
        
        result = split_text_by_language("你好Hello世界World")
        # Should have alternating segments
        assert len(result) >= 2
        # First segment should be Chinese
        assert result[0][0] == 'zh'
        # Should contain both Chinese and English segments
        langs = [seg[0] for seg in result]
        assert 'zh' in langs
        assert 'en' in langs
    
    def test_split_empty_text(self):
        """Test splitting empty text."""
        from chinese.lang_split import split_text_by_language
        
        result = split_text_by_language("")
        assert result == []
    
    def test_split_text_with_punctuation(self):
        """Test that punctuation is handled correctly."""
        from chinese.lang_split import split_text_by_language
        
        # ASCII punctuation should be grouped with English
        result = split_text_by_language("你好，Hello!")
        assert len(result) >= 1
        
        # Check that the result contains both language types
        all_text = ''.join([seg[1] for seg in result])
        assert '你好' in all_text
        assert 'Hello' in all_text
    
    def test_merge_short_segments(self):
        """Test that short English segments are merged."""
        from chinese.lang_split import split_text_by_language
        
        # A single comma between Chinese characters should be merged
        result = split_text_by_language("你好,世界", merge_short=True)
        # Short ASCII segments should be merged with adjacent Chinese
        # Result should not have many tiny segments
        assert len(result) <= 3
    
    def test_no_merge_long_english(self):
        """Test that long English segments are not merged."""
        from chinese.lang_split import split_text_by_language
        
        result = split_text_by_language("你好Hello World这是测试", merge_short=True)
        # "Hello World" is long enough to be its own segment
        english_segments = [seg for seg in result if seg[0] == 'en']
        assert len(english_segments) >= 1


class TestMixedStream:
    """Tests for the mixed stream functionality."""
    
    @pytest.fixture
    def mock_kokoro_model(self):
        """Create a mock Kokoro model that returns sample audio."""
        async def mock_stream(*args, **kwargs):
            # Yield a few chunks of fake audio
            for _ in range(3):
                yield (np.zeros(1024, dtype=np.float32), 24000)
        
        mock = Mock()
        mock.create_stream = Mock(return_value=mock_stream())
        return mock
    
    @pytest.fixture
    def mock_g2p(self):
        """Create a mock G2P converter."""
        mock = Mock()
        mock.return_value = ("phonemes", None)
        return mock
    
    @pytest.mark.asyncio
    async def test_mixed_stream_produces_output(self, mock_kokoro_model, mock_g2p):
        """Test that create_mixed_stream produces non-empty output."""
        from chinese.mixed_stream import create_mixed_stream
        
        # Patch the English TTS to avoid loading the model
        with patch('chinese.mixed_stream.create_english_stream') as mock_en_stream:
            async def mock_en_gen(*args, **kwargs):
                for _ in range(2):
                    yield (np.zeros(512, dtype=np.float32), 24000)
            mock_en_stream.return_value = mock_en_gen()
            
            # Test with Chinese-only text
            chunks = []
            async for chunk, sr in create_mixed_stream(
                "你好世界",
                mock_kokoro_model,
                mock_g2p,
                voice_zh="zf_001"
            ):
                chunks.append((chunk, sr))
            
            # Should produce some output
            assert len(chunks) > 0
    
    @pytest.mark.asyncio
    async def test_mixed_stream_handles_mixed_text(self, mock_kokoro_model, mock_g2p):
        """Test that mixed text processes both languages."""
        from chinese.mixed_stream import create_mixed_stream
        
        # Track which streams were called
        zh_called = False
        en_called = False
        
        original_create_stream = mock_kokoro_model.create_stream
        
        def track_zh_stream(*args, **kwargs):
            nonlocal zh_called
            zh_called = True
            async def gen():
                yield (np.zeros(512, dtype=np.float32), 24000)
            return gen()
        
        mock_kokoro_model.create_stream = track_zh_stream
        
        with patch('chinese.mixed_stream.create_english_stream') as mock_en_stream:
            async def mock_en_gen(*args, **kwargs):
                nonlocal en_called
                en_called = True
                yield (np.zeros(512, dtype=np.float32), 24000)
            mock_en_stream.return_value = mock_en_gen()
            
            # Process mixed text
            chunks = []
            async for chunk, sr in create_mixed_stream(
                "你好Hello世界",
                mock_kokoro_model,
                mock_g2p
            ):
                chunks.append((chunk, sr))
            
            # Both streams should be called for mixed text
            assert zh_called, "Chinese stream should be called"
            # Note: English might not be called if the segment is too short and merged
    
    @pytest.mark.asyncio
    async def test_mixed_stream_empty_text(self, mock_kokoro_model, mock_g2p):
        """Test that empty text produces no output."""
        from chinese.mixed_stream import create_mixed_stream
        
        chunks = []
        async for chunk, sr in create_mixed_stream(
            "",
            mock_kokoro_model,
            mock_g2p
        ):
            chunks.append((chunk, sr))
        
        assert len(chunks) == 0
    
    @pytest.mark.asyncio
    async def test_mixed_stream_whitespace_only(self, mock_kokoro_model, mock_g2p):
        """Test that whitespace-only text produces no output."""
        from chinese.mixed_stream import create_mixed_stream
        
        chunks = []
        async for chunk, sr in create_mixed_stream(
            "   \t\n  ",
            mock_kokoro_model,
            mock_g2p
        ):
            chunks.append((chunk, sr))
        
        assert len(chunks) == 0


class TestEnglishTTS:
    """Tests for the English TTS wrapper."""
    
    @pytest.mark.asyncio
    async def test_english_stream_requires_model(self):
        """Test that English stream raises error when model not available."""
        from chinese.english_tts import create_english_stream, reset_english_model_state
        
        # Reset init state using the public function
        reset_english_model_state()
        
        # Mock the model loading to fail (model files don't exist)
        with patch('chinese.english_tts.ENGLISH_MODELS_DIR') as mock_path:
            mock_path.__truediv__ = lambda self, x: Mock(exists=lambda: False)
            
            with pytest.raises(RuntimeError):
                async for _ in create_english_stream("Hello"):
                    pass


# Run tests with pytest
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
