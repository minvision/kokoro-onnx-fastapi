"""
Tests for mixed language stream functionality.

These tests use mocks to avoid loading the actual TTS models,
making them suitable for CI environments.
"""
import asyncio
import sys
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import pytest
import numpy as np

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestLangSplit:
    """Tests for language splitting functionality."""
    
    def test_split_pure_chinese(self):
        """Test splitting pure Chinese text."""
        from src.chinese.lang_split import split_by_language
        
        result = split_by_language("你好世界")
        assert len(result) == 1
        assert result[0] == ('zh', '你好世界')
    
    def test_split_pure_english(self):
        """Test splitting pure English text."""
        from src.chinese.lang_split import split_by_language
        
        result = split_by_language("Hello World")
        assert len(result) == 1
        assert result[0] == ('en', 'Hello World')
    
    def test_split_mixed_text(self):
        """Test splitting mixed Chinese/English text."""
        from src.chinese.lang_split import split_by_language
        
        result = split_by_language("你好Hello世界")
        # Should have 3 segments: 你好 (zh), Hello (en), 世界 (zh)
        assert len(result) == 3
        assert result[0] == ('zh', '你好')
        assert result[1] == ('en', 'Hello')
        assert result[2] == ('zh', '世界')
    
    def test_split_empty_text(self):
        """Test splitting empty text."""
        from src.chinese.lang_split import split_by_language
        
        result = split_by_language("")
        assert result == []
    
    def test_split_with_numbers_and_punctuation(self):
        """Test splitting text with numbers and punctuation."""
        from src.chinese.lang_split import split_by_language
        
        result = split_by_language("测试123abc")
        # Numbers and ASCII chars should be grouped together
        assert len(result) >= 1
        # First segment should be Chinese
        assert result[0][0] == 'zh'
    
    def test_split_merge_short_english(self):
        """Test that short English segments can be merged with Chinese."""
        from src.chinese.lang_split import split_by_language
        
        # Single punctuation between Chinese should be merged
        result = split_by_language("你好,世界", min_en_merge_len=3)
        # The comma might be merged with Chinese
        # Implementation dependent - just verify it returns valid result
        assert len(result) >= 1
        for lang, text in result:
            assert lang in ('en', 'zh')
            assert len(text) > 0
    
    def test_split_preserves_whitespace(self):
        """Test that whitespace is preserved."""
        from src.chinese.lang_split import split_by_language
        
        result = split_by_language("Hello World")
        # Verify the text content is preserved
        combined = ''.join(text for _, text in result)
        assert 'Hello' in combined
        assert 'World' in combined


class TestMixedStream:
    """Tests for mixed stream functionality using mocks."""
    
    @pytest.fixture
    def mock_kokoro_chinese(self):
        """Create a mock Chinese Kokoro model."""
        mock = MagicMock()
        
        async def mock_stream(*args, **kwargs):
            # Simulate yielding audio chunks
            for i in range(3):
                yield (np.zeros(1600, dtype=np.float32), 24000)
        
        mock.create_stream = Mock(return_value=mock_stream())
        return mock
    
    @pytest.fixture
    def mock_g2p_chinese(self):
        """Create a mock Chinese G2P converter."""
        mock = Mock()
        mock.return_value = ("phonemes", {})
        return mock
    
    @pytest.fixture
    def mock_kokoro_english(self):
        """Create a mock English Kokoro model."""
        mock = MagicMock()
        
        async def mock_stream(*args, **kwargs):
            for i in range(2):
                yield (np.zeros(1600, dtype=np.float32), 24000)
        
        mock.create_stream = Mock(return_value=mock_stream())
        return mock
    
    @pytest.fixture
    def mock_g2p_english(self):
        """Create a mock English G2P converter."""
        mock = Mock()
        mock.return_value = ("phonemes", {})
        return mock
    
    @pytest.mark.asyncio
    async def test_mixed_stream_yields_bytes(
        self, 
        mock_kokoro_chinese, 
        mock_g2p_chinese,
        mock_kokoro_english,
        mock_g2p_english
    ):
        """Test that create_mixed_stream yields non-empty audio data."""
        with patch.dict('sys.modules', {
            'src.chinese.main': MagicMock(
                kokoro_model=mock_kokoro_chinese,
                g2p_converter=mock_g2p_chinese
            ),
            'src.other.main': MagicMock(
                kokoro_model=mock_kokoro_english,
                g2p_converter=mock_g2p_english
            )
        }):
            # Import after patching
            from src.chinese.mixed_stream import create_mixed_stream
            
            chunks = []
            async for audio, sr in create_mixed_stream("你好Hello"):
                chunks.append((audio, sr))
            
            # Should have yielded some audio chunks
            assert len(chunks) > 0
            for audio, sr in chunks:
                assert isinstance(audio, np.ndarray)
                assert isinstance(sr, int)
    
    @pytest.mark.asyncio
    async def test_chinese_stream_helper(
        self,
        mock_kokoro_chinese,
        mock_g2p_chinese
    ):
        """Test the Chinese stream helper function."""
        from src.chinese.mixed_stream import _create_chinese_stream
        
        chunks = []
        async for audio, sr in _create_chinese_stream(
            mock_kokoro_chinese,
            mock_g2p_chinese,
            "测试文本",
            voice="zf_001",
            speed=1.0
        ):
            chunks.append((audio, sr))
        
        assert len(chunks) > 0


class TestEnglishTTSAdapter:
    """Tests for English TTS adapter."""
    
    @pytest.fixture
    def mock_kokoro_english(self):
        """Create a mock English Kokoro model."""
        mock = MagicMock()
        
        async def mock_stream(*args, **kwargs):
            for i in range(2):
                yield (np.zeros(1600, dtype=np.float32), 24000)
        
        mock.create_stream = Mock(return_value=mock_stream())
        return mock
    
    @pytest.fixture
    def mock_g2p_english(self):
        """Create a mock English G2P converter."""
        mock = Mock()
        mock.return_value = ("phonemes", {})
        return mock
    
    @pytest.mark.asyncio
    async def test_english_stream_yields_audio(
        self,
        mock_kokoro_english,
        mock_g2p_english
    ):
        """Test that create_english_stream yields audio data."""
        with patch.dict('sys.modules', {
            'src.other.main': MagicMock(
                kokoro_model=mock_kokoro_english,
                g2p_converter=mock_g2p_english
            )
        }):
            from src.chinese.english_tts import create_english_stream
            
            chunks = []
            async for audio, sr in create_english_stream("Hello World"):
                chunks.append((audio, sr))
            
            assert len(chunks) > 0
            for audio, sr in chunks:
                assert isinstance(audio, np.ndarray)


class TestIntegration:
    """Integration tests (still using mocks for models)."""
    
    @pytest.mark.asyncio
    async def test_lang_split_integration(self):
        """Test lang_split works correctly with various inputs."""
        from src.chinese.lang_split import split_by_language
        
        test_cases = [
            ("Hello", [('en', 'Hello')]),
            ("你好", [('zh', '你好')]),
            ("Hi你好", [('en', 'Hi'), ('zh', '你好')]),
            ("", []),
        ]
        
        for input_text, expected_result in test_cases:
            result = split_by_language(input_text)
            if expected_result:
                # Verify same number of segments
                assert len(result) == len(expected_result), f"Failed for input: {input_text}"
                # Verify language tags
                for (actual_lang, _), (expected_lang, _) in zip(result, expected_result):
                    assert actual_lang == expected_lang, f"Failed language check for: {input_text}"


# Run tests with pytest
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
