"""
Indexed content search tests.

Tests searching indexed documents via Search Proxy with correct signatures.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from app.tools.search_indexed import search_indexed_content


@pytest.fixture
def sample_search_response():
    """Sample search proxy response."""
    return {
        "results": [
            {
                "score": 0.95,
                "title": "HIRF Protection Guidelines",
                "source": "AC 20-161A",
                "content": "High-Intensity Radiated Fields (HIRF) protection requirements...",
                "chunk_id": "ac-20-161a-chunk-1"
            },
            {
                "score": 0.87,
                "title": "Environmental Conditions",
                "source": "14 CFR 25.1311",
                "content": "Aircraft must withstand environmental conditions including HIRF...",
                "chunk_id": "cfr-25-1311-chunk-2"
            }
        ],
        "total": 2
    }


@pytest.mark.unit
class TestSearchIndexed:
    """Tests for indexed content search."""
    
    @pytest.mark.asyncio
    async def test_search_returns_results(self, sample_search_response):
        """Test search returns formatted results."""
        with patch("app.tools.search_indexed.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=sample_search_response)
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with patch("app.tools.search_indexed.get_settings") as mock_settings:
                mock_settings_instance = mock_settings.return_value
                mock_settings_instance.azure_search_index = "faa-agent"
                mock_settings_instance.search_proxy_url = "http://localhost:8001"
                
                result = await search_indexed_content(
                    query="HIRF protection",
                    fingerprint="test-fingerprint"
                )
                
                assert isinstance(result, str)
                assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_search_respects_index_name(self, sample_search_response):
        """Test search respects index_name parameter."""
        with patch("app.tools.search_indexed.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=sample_search_response)
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with patch("app.tools.search_indexed.get_settings") as mock_settings:
                mock_settings_instance = mock_settings.return_value
                mock_settings_instance.azure_search_index = "faa-agent"
                mock_settings_instance.search_proxy_url = "http://localhost:8001"
                
                result = await search_indexed_content(
                    query="test",
                    index_name="nrc-agent",
                    fingerprint="test-fingerprint"
                )
                
                # Verify POST was called with correct index
                call_args = mock_client.post.call_args
                assert call_args is not None
                json_data = call_args[1]["json"]
                assert json_data["index"] == "nrc-agent"
    
    @pytest.mark.asyncio
    async def test_search_filters_by_fingerprint(self, sample_search_response):
        """Test search includes fingerprint for isolation."""
        with patch("app.tools.search_indexed.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=sample_search_response)
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with patch("app.tools.search_indexed.get_settings") as mock_settings:
                mock_settings_instance = mock_settings.return_value
                mock_settings_instance.azure_search_index = "faa-agent"
                mock_settings_instance.search_proxy_url = "http://localhost:8001"
                
                test_fingerprint = "user-fingerprint-123"
                result = await search_indexed_content(
                    query="test",
                    fingerprint=test_fingerprint
                )
                
                # Verify fingerprint in request
                call_args = mock_client.post.call_args
                json_data = call_args[1]["json"]
                assert json_data["fingerprint"] == test_fingerprint
                
                # Verify fingerprint in request
                call_args = mock_client.post.call_args
                json_data = call_args[1]["json"]
                assert json_data["fingerprint"] == test_fingerprint
    
    @pytest.mark.asyncio
    async def test_search_handles_no_results(self):
        """Test search handles no results."""
        empty_response = {"results": [], "total": 0}
        
        with patch("app.tools.search_indexed.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=empty_response)
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with patch("app.tools.search_indexed.get_settings") as mock_settings:
                mock_settings_instance = mock_settings.return_value
                mock_settings_instance.azure_search_index = "faa-agent"
                mock_settings_instance.search_proxy_url = "http://localhost:8001"
                
                result = await search_indexed_content(
                    query="nonexistent-topic",
                    fingerprint="test-fingerprint"
                )
                
                assert isinstance(result, str)
    
    @pytest.mark.asyncio
    async def test_search_handles_api_error(self):
        """Test search handles API errors."""
        with patch("app.tools.search_indexed.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.raise_for_status = Mock(side_effect=Exception("API Error"))
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with patch("app.tools.search_indexed.get_settings") as mock_settings:
                mock_settings_instance = mock_settings.return_value
                mock_settings_instance.azure_search_index = "faa-agent"
                mock_settings_instance.search_proxy_url = "http://localhost:8001"
                
                result = await search_indexed_content(
                    query="test",
                    fingerprint="test-fingerprint"
                )
                
                assert "error" in result.lower()
    
    @pytest.mark.asyncio
    async def test_search_respects_top_k(self, sample_search_response):
        """Test search respects top_k parameter."""
        with patch("app.tools.search_indexed.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=sample_search_response)
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with patch("app.tools.search_indexed.get_settings") as mock_settings:
                mock_settings_instance = mock_settings.return_value
                mock_settings_instance.azure_search_index = "faa-agent"
                mock_settings_instance.search_proxy_url = "http://localhost:8001"
                
                result = await search_indexed_content(
                    query="test",
                    top_k=10,
                    fingerprint="test-fingerprint"
                )
                    # Verify top_k in request (capped at 20)
                call_args = mock_client.post.call_args
                json_data = call_args[1]["json"]
                assert json_data["top"] == 10


@pytest.mark.unit
class TestSearchFiltering:
    """Tests for search filtering."""
    
    @pytest.mark.asyncio
    async def test_search_filters_by_doc_type(self, sample_search_response):
        """Test search can filter by document type."""
        with patch("app.tools.search_indexed.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=sample_search_response)
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with patch("app.tools.search_indexed.get_settings") as mock_settings:
                mock_settings_instance = mock_settings.return_value
                mock_settings_instance.azure_search_index = "faa-agent"
                mock_settings_instance.search_proxy_url = "http://localhost:8001"
                
                result = await search_indexed_content(
                    query="test",
                    doc_type="ac",
                    fingerprint="test-fingerprint"
                )
                
                # Verify doc_type in request
                call_args = mock_client.post.call_args
                json_data = call_args[1]["json"]
                assert json_data.get("doc_type") == "ac"


@pytest.mark.unit
class TestSearchValidation:
    """Tests for search input validation."""
    
    @pytest.mark.asyncio
    async def test_search_requires_query(self):
        """Test search requires query parameter."""
        with patch("app.tools.search_indexed.get_settings") as mock_settings:
            mock_settings.return_value.azure_search_index = "faa-agent"
            mock_settings.return_value.search_proxy_url = "http://localhost:8001"
            
            # Should handle empty query gracefully
            result = await search_indexed_content(
                query="",
                fingerprint="test-fingerprint"
            )
            
            # Should return something (either empty results or prompt for query)
            assert isinstance(result, str)


@pytest.mark.unit
class TestSearchIntegration:
    """Integration tests for search."""
    
    @pytest.mark.asyncio
    async def test_search_workflow_complete(self, sample_search_response):
        """Test complete search workflow."""
        with patch("app.tools.search_indexed.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=sample_search_response)
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with patch("app.tools.search_indexed.get_settings") as mock_settings:
                mock_settings_instance = mock_settings.return_value
                mock_settings_instance.azure_search_index = "faa-agent"
                mock_settings_instance.search_proxy_url = "http://localhost:8001"
                
                result = await search_indexed_content(
                    query="HIRF protection requirements",
                    top_k=5,
                    index_name="faa-agent",
                    fingerprint="user-123"
                )
                
                assert isinstance(result, str)
                assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_multiple_searches_with_different_queries(self, sample_search_response):
        """Test multiple searches with different queries."""
        with patch("app.tools.search_indexed.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=sample_search_response)
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with patch("app.tools.search_indexed.get_settings") as mock_settings:
                mock_settings_instance = mock_settings.return_value
                mock_settings_instance.azure_search_index = "faa-agent"
                mock_settings_instance.search_proxy_url = "http://localhost:8001"
                
                # Search 1
                result1 = await search_indexed_content(
                    query="HIRF",
                    fingerprint="user-123"
                )
                
                # Search 2
                result2 = await search_indexed_content(
                    query="environmental conditions",
                    fingerprint="user-123"
                )
                
                # Both should return results
                assert isinstance(result1, str)
                assert isinstance(result2, str)
                assert len(result1) > 0
                assert len(result2) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
