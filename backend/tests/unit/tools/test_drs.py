"""
DRS (Dynamic Regulatory System) API tool tests.

Tests searching FAA documents via DRS API with correct function signatures.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from app.tools.drs import search_drs


@pytest.fixture
def sample_drs_search_response():
    """Sample DRS API search response."""
    return {
        "summary": {
            "doctypeName": "AC",
            "drsDoctypeName": "Advisory Circulars (AC)",
            "count": 2,
            "hasMoreItems": False,
            "totalItems": 2,
            "offset": 0,
            "sortBy": "drs:approvalDate",
            "sortByOrder": "DESC"
        },
        "documents": [
            {
                "documentGuid": "guid-1",
                "drs:documentNumber": "20-161A",
                "drs:title": "HIRF Protection of Aircraft Electrical and Electronic Systems",
                "drs:approvalDate": "2013-07-01",
                "drs:status": "Current",
                "drs:partNumber": ["25"],
                "mainDocumentDownloadURL": "https://drs.faa.gov/api/drs/data-pull/download/guid-1",
                "mainDocumentFileName": "AC_20-161A.pdf"
            }
        ]
    }


@pytest.mark.unit
class TestDRSSearch:
    """Tests for DRS document search."""
    
    @pytest.mark.asyncio
    async def test_search_drs_by_keywords(self, sample_drs_search_response):
        """Test searching DRS by keywords (list)."""
        with patch("app.tools.drs.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            # response.json() is NOT async in httpx, returns directly
            mock_response.json = Mock(return_value=sample_drs_search_response)
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with patch("app.tools.drs.get_settings") as mock_settings:
                mock_settings_instance = mock_settings.return_value
                mock_settings_instance.drs_api_base_url = "https://drs.faa.gov/api/drs"
                mock_settings_instance.drs_api_key = "test-key"
                
                result = await search_drs(keywords=["HIRF"], doc_type="AC")
                
                assert isinstance(result, str)
                assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_search_drs_filters_by_type(self, sample_drs_search_response):
        """Test DRS search with document type filter."""
        with patch("app.tools.drs.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=sample_drs_search_response)
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with patch("app.tools.drs.get_settings") as mock_settings:
                mock_settings_instance = mock_settings.return_value
                mock_settings_instance.drs_api_base_url = "https://drs.faa.gov/api/drs"
                mock_settings_instance.drs_api_key = "test-key"
                
                result = await search_drs(keywords=["test"], doc_type="AD")
                
                assert isinstance(result, str)
    
    @pytest.mark.asyncio
    async def test_search_drs_handles_no_results(self):
        """Test DRS search with no results."""
        empty_response = {"documents": []}
        
        with patch("app.tools.drs.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=empty_response)
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with patch("app.tools.drs.get_settings") as mock_settings:
                mock_settings_instance = mock_settings.return_value
                mock_settings_instance.drs_api_base_url = "https://drs.faa.gov/api/drs"
                mock_settings_instance.drs_api_key = "test-key"
                
                result = await search_drs(keywords=["nonexistent"])
                
                assert "found" in result.lower()
    
    @pytest.mark.asyncio
    async def test_search_drs_handles_api_error(self):
        """Test DRS search handles API errors."""
        with patch("app.tools.drs.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.raise_for_status = Mock(side_effect=Exception("API Error"))
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with patch("app.tools.drs.get_settings") as mock_settings:
                mock_settings_instance = mock_settings.return_value
                mock_settings_instance.drs_api_base_url = "https://drs.faa.gov/api/drs"
                mock_settings_instance.drs_api_key = "test-key"
                
                result = await search_drs(keywords=["test"])
                
                assert "error" in result.lower()
    
    @pytest.mark.asyncio
    async def test_search_drs_with_status_filter(self, sample_drs_search_response):
        """Test DRS search with status filter."""
        with patch("app.tools.drs.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=sample_drs_search_response)
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with patch("app.tools.drs.get_settings") as mock_settings:
                mock_settings_instance = mock_settings.return_value
                mock_settings_instance.drs_api_base_url = "https://drs.faa.gov/api/drs"
                mock_settings_instance.drs_api_key = "test-key"
                
                result = await search_drs(
                    keywords=["test"],
                    status_filter=["Current", "Historical"]
                )
                
                assert isinstance(result, str)


@pytest.mark.unit
class TestDRSDocumentTypes:
    """Tests for different DRS document types."""
    
    @pytest.mark.asyncio
    async def test_search_advisory_circulars(self, sample_drs_search_response):
        """Test searching for Advisory Circulars (AC)."""
        with patch("app.tools.drs.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=sample_drs_search_response)
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with patch("app.tools.drs.get_settings") as mock_settings:
                mock_settings_instance = mock_settings.return_value
                mock_settings_instance.drs_api_base_url = "https://drs.faa.gov/api/drs"
                mock_settings_instance.drs_api_key = "test-key"
                
                result = await search_drs(keywords=["test"], doc_type="AC")
                
                assert isinstance(result, str)
    
    @pytest.mark.asyncio
    async def test_search_airworthiness_directives(self, sample_drs_search_response):
        """Test searching for Airworthiness Directives (AD)."""
        with patch("app.tools.drs.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=sample_drs_search_response)
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with patch("app.tools.drs.get_settings") as mock_settings:
                mock_settings_instance = mock_settings.return_value
                mock_settings_instance.drs_api_base_url = "https://drs.faa.gov/api/drs"
                mock_settings_instance.drs_api_key = "test-key"
                
                result = await search_drs(keywords=["test"], doc_type="AD")
                
                assert isinstance(result, str)


@pytest.mark.unit
class TestDRSIntegration:
    """Integration tests for DRS tools."""
    
    @pytest.mark.asyncio
    async def test_search_workflow(self, sample_drs_search_response):
        """Test complete DRS search workflow."""
        with patch("app.tools.drs.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.json = Mock(return_value=sample_drs_search_response)
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with patch("app.tools.drs.get_settings") as mock_settings:
                mock_settings_instance = mock_settings.return_value
                mock_settings_instance.drs_api_base_url = "https://drs.faa.gov/api/drs"
                mock_settings_instance.drs_api_key = "test-key"
                
                result = await search_drs(
                    keywords=["HIRF", "protection"],
                    doc_type="AC",
                    max_results=5
                )
                
                assert isinstance(result, str)
                assert len(result) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
