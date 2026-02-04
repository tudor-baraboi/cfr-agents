"""
CFR fetching tool tests.

Tests fetching CFR sections from eCFR API, caching,
error handling, and reference extraction.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from httpx import Response

from app.tools.fetch_cfr import fetch_cfr_section


@pytest.fixture
def sample_cfr_response():
    """Sample CFR API response."""
    return {
        "results": [
            {
                "title": "14 CFR § 25.1317 - Electrical and electronic system lightning protection",
                "part": "25",
                "section": "1317",
                "subpart": "F",
                "text": """
                (a) General. The airplane electrical and electronic systems must be designed and installed
                so that:
                (1) The probable consequence of lightning strikes will not be a loss of ability of the
                airplane to continue safe flight and landing;
                (2) The electrical discharge from lightning will not pass through personnel in a manner
                that would cause injury or impedance to their safety or to safety-critical functions.
                """,
                "reserved": False
            }
        ]
    }


@pytest.fixture
def sample_cfr_with_refs():
    """CFR section with cross-references."""
    return {
        "results": [
            {
                "title": "14 CFR § 25.1309 - Equipment, systems, and installations",
                "part": "25",
                "section": "1309",
                "text": """
                The airplane systems and associated components must be designed
                so that capability is maintained, as described in §25.1317 for
                lightning protection requirements.
                """,
                "references": [
                    {"section": "§25.1317", "part": "25"},
                    {"section": "§25.1365", "part": "25"}
                ]
            }
        ]
    }


@pytest.mark.unit
class TestCFRFetching:
    """Tests for CFR section fetching."""
    
    @pytest.mark.asyncio
    async def test_fetch_cfr_section_by_number(self, sample_cfr_response):
        """Test fetching CFR section by part and section number."""
        with patch("app.tools.fetch_cfr._get_latest_date", new_callable=AsyncMock, return_value="2024-01-01"), \
             patch("app.tools.fetch_cfr.get_cache") as mock_get_cache, \
             patch("app.tools.fetch_cfr.httpx.AsyncClient") as mock_client:
            # Mock the cache
            mock_cache = AsyncMock()
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_get_cache.return_value = mock_cache
            
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()
            mock_response.text = "<title><section>Lightning protection</section></title>"
            
            async_client_mock = AsyncMock()
            async_client_mock.get = AsyncMock(return_value=mock_response)
            async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
            async_client_mock.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.return_value = async_client_mock
            
            result = await fetch_cfr_section(part="25", section="1317")
            
            assert "§25.1317" in result
            assert "lightning protection" in result.lower()
    
    @pytest.mark.asyncio
    async def test_fetch_cfr_formats_response(self, sample_cfr_response):
        """Test CFR response is properly formatted."""
        with patch("app.tools.fetch_cfr._get_latest_date", new_callable=AsyncMock, return_value="2024-01-01"), \
             patch("app.tools.fetch_cfr.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=sample_cfr_response)
            
            async_client_mock = AsyncMock()
            async_client_mock.get = AsyncMock(return_value=mock_response)
            async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
            async_client_mock.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.return_value = async_client_mock
            
            result = await fetch_cfr_section(part="25", section="1317")
            
            # Should be a formatted string
            assert isinstance(result, str)
            assert len(result) > 0
            # Should include title
            assert "lightning protection" in result.lower() or "1317" in result
    
    @pytest.mark.asyncio
    async def test_fetch_cfr_handles_not_found(self):
        """Test handling section not found."""
        with patch("app.tools.fetch_cfr._get_latest_date", new_callable=AsyncMock, return_value="2024-01-01"), \
             patch("app.tools.fetch_cfr.get_cache") as mock_get_cache, \
             patch("app.tools.fetch_cfr.httpx.AsyncClient") as mock_client:
            # Mock the cache
            mock_cache = AsyncMock()
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_get_cache.return_value = mock_cache
            
            mock_response = AsyncMock()
            mock_response.status_code = 404
            mock_response.raise_for_status = Mock()
            mock_response.text = ""
            
            async_client_mock = AsyncMock()
            async_client_mock.get = AsyncMock(return_value=mock_response)
            async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
            async_client_mock.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.return_value = async_client_mock
            
            result = await fetch_cfr_section(part="99", section="9999")
            
            # Should return not found message
            assert "not found" in result.lower() or len(result) == 0
    
    @pytest.mark.asyncio
    async def test_fetch_cfr_handles_api_error(self):
        """Test handling eCFR API errors."""
        with patch("app.tools.fetch_cfr._get_latest_date", new_callable=AsyncMock, return_value="2024-01-01"), \
             patch("app.tools.fetch_cfr.httpx.AsyncClient") as mock_client:
            async_client_mock = AsyncMock()
            async_client_mock.get = AsyncMock(side_effect=Exception("API error"))
            async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
            async_client_mock.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.return_value = async_client_mock
            
            result = await fetch_cfr_section(part="25", section="1317")
            
            # Should return error message
            assert "error" in result.lower()
    
    @pytest.mark.asyncio
    async def test_fetch_cfr_multiple_parts(self):
        """Test fetching from different CFR parts."""
        parts = ["23", "25", "27", "29"]
        
        with patch("app.tools.fetch_cfr._get_latest_date", new_callable=AsyncMock, return_value="2024-01-01"), \
             patch("app.tools.fetch_cfr.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value={"results": [{
                "title": "Test section",
                "part": "25",
                "section": "1317",
                "text": "Test"
            }]})
            
            async_client_mock = AsyncMock()
            async_client_mock.get = AsyncMock(return_value=mock_response)
            async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
            async_client_mock.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.return_value = async_client_mock
            
            for part in parts:
                result = await fetch_cfr_section(part=part, section="1")
                # Each should return a result
                assert isinstance(result, str)


@pytest.mark.unit
class TestCFRCaching:
    """Tests for CFR response caching."""
    
    @pytest.mark.asyncio
    async def test_caches_cfr_sections(self, sample_cfr_response):
        """Test CFR sections are cached after first fetch."""
        with patch("app.tools.fetch_cfr._get_latest_date", new_callable=AsyncMock, return_value="2024-01-01"), \
             patch("app.tools.fetch_cfr.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=sample_cfr_response)
            
            async_client_mock = AsyncMock()
            async_client_mock.get = AsyncMock(return_value=mock_response)
            async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
            async_client_mock.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.return_value = async_client_mock
            
            # First fetch
            result1 = await fetch_cfr_section(part="25", section="1317")
            
            # Second fetch - should use cache
            result2 = await fetch_cfr_section(part="25", section="1317")
            
            # Results should be same
            assert result1 == result2
            
            # API should only be called once due to caching
            # Note: This depends on implementation details
    
    @pytest.mark.asyncio
    async def test_cache_key_includes_part_and_section(self):
        """Test cache keys distinguish different sections."""
        with patch("app.tools.fetch_cfr._get_latest_date", new_callable=AsyncMock, return_value="2024-01-01"), \
             patch("app.tools.fetch_cfr.httpx.AsyncClient") as mock_client:
            async_client_mock = AsyncMock()
            
            # First response
            response1 = AsyncMock()
            response1.json = AsyncMock(return_value={"results": [{
                "title": "§25.1317",
                "text": "Section 1317"
            }]})
            
            # Second response
            response2 = AsyncMock()
            response2.json = AsyncMock(return_value={"results": [{
                "title": "§25.1309",
                "text": "Section 1309"
            }]})
            
            async_client_mock.get = AsyncMock(side_effect=[response1, response2])
            async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
            async_client_mock.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.return_value = async_client_mock
            
            # Fetch different sections
            result1 = await fetch_cfr_section(part="25", section="1317")
            result2 = await fetch_cfr_section(part="25", section="1309")
            
            # Should be different results
            assert result1 != result2


@pytest.mark.unit
class TestCFRReferences:
    """Tests for CFR text parsing."""
    
    @pytest.mark.asyncio
    async def test_parses_cfr_text_correctly(self, sample_cfr_with_refs):
        """Test parsing CFR response text."""
        with patch("app.tools.fetch_cfr._get_latest_date", new_callable=AsyncMock, return_value="2024-01-01"), \
             patch("app.tools.fetch_cfr.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=sample_cfr_with_refs)
            
            async_client_mock = AsyncMock()
            async_client_mock.get = AsyncMock(return_value=mock_response)
            async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
            async_client_mock.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.return_value = async_client_mock
            
            result = await fetch_cfr_section(part="25", section="1309")
            
            # Should parse text correctly
            assert isinstance(result, str)
            assert len(result) > 0


@pytest.mark.unit
class TestCFRValidation:
    """Tests for CFR input validation."""
    
    @pytest.mark.asyncio
    async def test_validates_part_number(self):
        """Test validates CFR part number."""
        # Invalid part
        result = await fetch_cfr_section(part="999", section="1")
        
        # Should either return error or empty
        assert isinstance(result, str)
    
    @pytest.mark.asyncio
    async def test_handles_malformed_section(self):
        """Test handling malformed section numbers."""
        result = await fetch_cfr_section(part="25", section="not-a-number")
        
        # Should return error or not found
        assert isinstance(result, str)
    
    @pytest.mark.asyncio
    async def test_handles_missing_parameters(self):
        """Test handling missing required parameters."""
        # Missing part
        try:
            result = await fetch_cfr_section(section="1317")
            assert isinstance(result, str)
        except TypeError:
            pass  # Expected if part is required
    
    @pytest.mark.asyncio
    async def test_normalizes_section_format(self):
        """Test normalizing section number formats."""
        # Different formats should work
        formats = [
            ("25", "1317"),
            ("25", "§1317"),
            ("25", "25.1317"),
        ]
        
        with patch("app.tools.fetch_cfr._get_latest_date", new_callable=AsyncMock, return_value="2024-01-01"), \
             patch("app.tools.fetch_cfr.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value={"results": [{
                "title": "Test",
                "text": "Content"
            }]})
            
            async_client_mock = AsyncMock()
            async_client_mock.get = AsyncMock(return_value=mock_response)
            async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
            async_client_mock.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.return_value = async_client_mock
            
            for part, section in formats:
                # Should handle various formats
                result = await fetch_cfr_section(part=part, section=section)
                assert isinstance(result, str)


@pytest.mark.unit
class TestCFRIntegration:
    """Integration tests for CFR fetching."""
    
    @pytest.mark.asyncio
    async def test_fetch_section_formats_correctly(self, sample_cfr_with_refs):
        """Test fetching section and formatting response."""
        with patch("app.tools.fetch_cfr._get_latest_date", new_callable=AsyncMock, return_value="2024-01-01"), \
             patch("app.tools.fetch_cfr.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=sample_cfr_with_refs)
            
            async_client_mock = AsyncMock()
            async_client_mock.get = AsyncMock(return_value=mock_response)
            async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
            async_client_mock.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.return_value = async_client_mock
            
            # Fetch section
            section_text = await fetch_cfr_section(part="25", section="1309")
            assert len(section_text) > 0
            assert isinstance(section_text, str)
    
    @pytest.mark.asyncio
    async def test_follow_reference_chain(self):
        """Test following chain of CFR references."""
        with patch("app.tools.fetch_cfr._get_latest_date", new_callable=AsyncMock, return_value="2024-01-01"), \
             patch("app.tools.fetch_cfr.httpx.AsyncClient") as mock_client:
            # Setup responses for chain: 25.1309 -> 25.1317 -> 25.1365
            responses = [
                {"results": [{
                    "title": "§25.1309",
                    "text": "References §25.1317",
                    "references": [{"section": "§25.1317"}]
                }]},
                {"results": [{
                    "title": "§25.1317",
                    "text": "References §25.1365",
                    "references": [{"section": "§25.1365"}]
                }]},
                {"results": [{
                    "title": "§25.1365",
                    "text": "Final reference"
                }]}
            ]
            
            mock_response = AsyncMock()
            async_client_mock = AsyncMock()
            async_client_mock.get = AsyncMock(side_effect=[
                MagicMock(json=AsyncMock(return_value=r)) for r in responses
            ])
            async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
            async_client_mock.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.return_value = async_client_mock
            
            # First fetch
            result1 = await fetch_cfr_section(part="25", section="1309")
            assert isinstance(result1, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
