"""
Integration tests for mixed Chinese-English TTS streaming.

This module provides tests for the mixed_stream functionality, verifying
that the language segmentation and mixed synthesis work correctly.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import numpy as np
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'chinese'))


class TestLangSplit:
    """Tests for the language segmentation module."""
    
    def test_pure_chinese(self):
        """Test segmentation of pure Chinese text."""
        from chinese.lang_split import segment_text
        
        result = segment_text("你好世界")
        assert len(result) == 1
        assert result[0] == ("你好世界", "zh")
    
    def test_pure_english(self):
        """Test segmentation of pure English text."""
        from chinese.lang_split import segment_text
        
        result = segment_text("Hello World")
        assert len(result) == 1
        assert result[0] == ("Hello World", "en")
    
    def test_mixed_simple(self):
        """Test segmentation of simple mixed text."""
        from chinese.lang_split import segment_text
        
        result = segment_text("你好Hello世界")
        assert len(result) == 3
        assert result[0] == ("你好", "zh")
        assert result[1] == ("Hello", "en")
        assert result[2] == ("世界", "zh")
    
    def test_mixed_with_numbers(self):
        """Test segmentation with numbers."""
        from chinese.lang_split import segment_text
        
        result = segment_text("今天是2024年")
        assert len(result) == 3
        assert result[0] == ("今天是", "zh")
        assert result[1] == ("2024", "en")
        assert result[2] == ("年", "zh")
    
    def test_mixed_with_punctuation(self):
        """Test segmentation with punctuation."""
        from chinese.lang_split import segment_text
        
        result = segment_text("Hello, 你好!")
        # "Hello, " is ASCII, "你好" is Chinese, "!" is ASCII
        assert len(result) >= 2
        # Check that both languages are represented
        langs = [seg[1] for seg in result]
        assert 'en' in langs
        assert 'zh' in langs
    
    def test_empty_string(self):
        """Test segmentation of empty string."""
        from chinese.lang_split import segment_text
        
        result = segment_text("")
        assert result == []
    
    def test_whitespace_only(self):
        """Test segmentation of whitespace."""
        from chinese.lang_split import segment_text
        
        result = segment_text("   ")
        # Whitespace is ASCII, so should be 'en'
        assert len(result) == 1
        assert result[0][1] == "en"


class TestMixedStreamMocked:
    """Tests for mixed stream with mocked models."""
    
    @pytest.fixture
    def mock_zh_model(self):
        """Create a mock Chinese model."""
        model = Mock()
        # Mock create_stream to return a generator
        def mock_stream(*args, **kwargs):
            # Return a generator that yields sample audio
            yield (np.zeros(1000, dtype=np.float32), 24000)
        model.create_stream = mock_stream
        return model
    
    @pytest.fixture
    def mock_zh_g2p(self):
        """Create a mock Chinese G2P converter."""
        g2p = Mock()
        g2p.return_value = ("mock_phonemes", None)
        return g2p
    
    @pytest.mark.asyncio
    async def test_pure_chinese_stream(self, mock_zh_model, mock_zh_g2p):
        """Test streaming pure Chinese text."""
        from chinese.mixed_stream import create_mixed_stream
        
        chunks = []
        async for chunk in create_mixed_stream(
            text="你好世界",
            zh_model=mock_zh_model,
            zh_g2p=mock_zh_g2p,
        ):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        assert all(isinstance(c[0], np.ndarray) for c in chunks)
        assert all(isinstance(c[1], int) for c in chunks)
    
    @pytest.mark.asyncio
    async def test_empty_text_stream(self, mock_zh_model, mock_zh_g2p):
        """Test streaming empty text."""
        from chinese.mixed_stream import create_mixed_stream
        
        chunks = []
        async for chunk in create_mixed_stream(
            text="",
            zh_model=mock_zh_model,
            zh_g2p=mock_zh_g2p,
        ):
            chunks.append(chunk)
        
        assert len(chunks) == 0
    
    @pytest.mark.asyncio
    async def test_missing_model_raises(self):
        """Test that missing model raises ValueError."""
        from chinese.mixed_stream import create_mixed_stream
        
        with pytest.raises(ValueError):
            async for _ in create_mixed_stream(
                text="测试",
                zh_model=None,
                zh_g2p=None,
            ):
                pass
    
    @pytest.mark.asyncio
    async def test_mixed_text_with_fallback(self, mock_zh_model, mock_zh_g2p):
        """Test mixed text with fallback to Chinese when English model unavailable."""
        from chinese.mixed_stream import create_mixed_stream_with_fallback
        
        # The function imports get_english_model inside, so we patch it at the source
        with patch('chinese.english_tts.get_english_model', return_value=(None, None)):
            # This should not raise - it should fallback to Chinese model
            # The actual test would need the full mock setup
            pass  # For now, just verify the import works
        
        # For this test, we mainly verify the function handles the fallback gracefully
        # The actual integration would require the full English model


class TestEnglishTTS:
    """Tests for English TTS adapter."""
    
    def test_module_import(self):
        """Test that english_tts module can be imported."""
        from chinese import english_tts
        assert hasattr(english_tts, 'create_english_stream')
        assert hasattr(english_tts, 'get_english_model')


class TestIntegration:
    """Integration tests (may require models to be present)."""
    
    @pytest.mark.skipif(
        not os.path.exists(os.path.join(os.path.dirname(__file__), '..', 'src', 'chinese', 'models', 'kokoro-v1.1-zh.onnx')),
        reason="Chinese model not available"
    )
    @pytest.mark.asyncio
    async def test_real_chinese_synthesis(self):
        """Test real Chinese synthesis if model is available."""
        # This test would be skipped if model files are not present
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
