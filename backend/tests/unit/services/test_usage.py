"""
Usage tracking and quota management tests.

Tests the UsageTracker class that manages daily request quotas
backed by Azure Table Storage.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from azure.core.exceptions import ResourceNotFoundError

from app.services.usage import UsageTracker, get_usage_tracker


@pytest.fixture
def test_fingerprint():
    """Test fingerprint."""
    return "test-fp-12345"


@pytest.fixture
def tracker():
    """UsageTracker instance for testing."""
    return UsageTracker()


@pytest.mark.unit
class TestUsageTrackerInitialization:
    """Tests for UsageTracker initialization."""
    
    def test_tracker_initializes(self):
        """Test tracker can be instantiated."""
        tracker = UsageTracker()
        assert tracker is not None
        assert tracker._client is None
        assert tracker._table is None
    
    def test_get_usage_tracker_returns_singleton(self):
        """Test get_usage_tracker returns a singleton."""
        tracker1 = get_usage_tracker()
        tracker2 = get_usage_tracker()
        assert tracker1 is tracker2


@pytest.mark.unit
class TestPartitionKey:
    """Tests for partition key generation."""
    
    def test_today_partition_returns_date_string(self, tracker):
        """Test partition key is formatted as YYYY-MM-DD."""
        partition = tracker._today_partition()
        
        # Should be in YYYY-MM-DD format
        assert len(partition) == 10
        assert partition[4] == "-"
        assert partition[7] == "-"
        
        # Should be parseable
        parsed = datetime.strptime(partition, "%Y-%m-%d")
        assert parsed is not None


@pytest.mark.unit
class TestGetUsage:
    """Tests for get_usage method."""
    
    @pytest.mark.asyncio
    async def test_get_usage_returns_zero_for_new_fingerprint(self, tracker, test_fingerprint):
        """Test get_usage returns 0 for non-existent fingerprint."""
        mock_table = AsyncMock()
        mock_table.get_entity = AsyncMock(side_effect=ResourceNotFoundError())
        tracker._table = mock_table
        
        result = await tracker.get_usage(test_fingerprint)
        
        assert result == 0
    
    @pytest.mark.asyncio
    async def test_get_usage_returns_count(self, tracker, test_fingerprint):
        """Test get_usage returns request count from entity."""
        mock_table = AsyncMock()
        mock_entity = {"RequestCount": 5}
        mock_table.get_entity = AsyncMock(return_value=mock_entity)
        tracker._table = mock_table
        
        result = await tracker.get_usage(test_fingerprint)
        
        assert result == 5
        mock_table.get_entity.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_usage_handles_missing_count(self, tracker, test_fingerprint):
        """Test get_usage returns 0 if RequestCount is missing."""
        mock_table = AsyncMock()
        mock_entity = {}  # No RequestCount
        mock_table.get_entity = AsyncMock(return_value=mock_entity)
        tracker._table = mock_table
        
        result = await tracker.get_usage(test_fingerprint)
        
        assert result == 0


@pytest.mark.unit
class TestIncrementUsage:
    """Tests for increment_usage method."""
    
    @pytest.mark.asyncio
    async def test_increment_usage_creates_new_entity(self, tracker, test_fingerprint):
        """Test increment_usage creates entity for new fingerprint."""
        mock_table = AsyncMock()
        mock_table.get_entity = AsyncMock(side_effect=ResourceNotFoundError())
        mock_table.create_entity = AsyncMock()
        tracker._table = mock_table
        
        with patch("app.services.geolocation.get_location_from_ip", new_callable=AsyncMock):
            result = await tracker.increment_usage(test_fingerprint)
        
        assert result == 1
        mock_table.create_entity.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_increment_usage_updates_existing_entity(self, tracker, test_fingerprint):
        """Test increment_usage increments count for existing fingerprint."""
        mock_table = AsyncMock()
        mock_entity = {"RequestCount": 3, "PartitionKey": "2024-01-01", "RowKey": test_fingerprint}
        mock_table.get_entity = AsyncMock(return_value=mock_entity)
        mock_table.update_entity = AsyncMock()
        tracker._table = mock_table
        
        with patch("app.services.geolocation.get_location_from_ip", new_callable=AsyncMock):
            result = await tracker.increment_usage(test_fingerprint)
        
        assert result == 4
        mock_table.update_entity.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_increment_usage_with_location(self, tracker, test_fingerprint):
        """Test increment_usage stores location data when IP provided."""
        mock_table = AsyncMock()
        mock_table.get_entity = AsyncMock(side_effect=ResourceNotFoundError())
        mock_table.create_entity = AsyncMock()
        tracker._table = mock_table
        
        location = {"city": "San Francisco", "country": "US"}
        with patch("app.services.geolocation.get_location_from_ip", new_callable=AsyncMock, return_value=location):
            result = await tracker.increment_usage(
                test_fingerprint,
                ip_address="192.168.1.1"
            )
        
        assert result == 1
        # Verify create_entity was called
        mock_table.create_entity.assert_called_once()
        call_args = mock_table.create_entity.call_args[0][0]
        assert call_args["IPAddress"] == "192.168.1.1"
        assert call_args["Country"] == "US"


@pytest.mark.unit
class TestGetRemaining:
    """Tests for get_remaining method."""
    
    @pytest.mark.asyncio
    async def test_get_remaining_calculates_correctly(self, tracker, test_fingerprint):
        """Test get_remaining returns (used, remaining) tuple."""
        mock_table = AsyncMock()
        mock_entity = {"RequestCount": 3}
        mock_table.get_entity = AsyncMock(return_value=mock_entity)
        tracker._table = mock_table
        
        with patch.object(tracker._settings, 'daily_request_limit', 10):
            used, remaining = await tracker.get_remaining(test_fingerprint, limit=10)
        
        assert used == 3
        assert remaining == 7
    
    @pytest.mark.asyncio
    async def test_get_remaining_uses_default_limit(self, tracker, test_fingerprint):
        """Test get_remaining uses settings limit when not provided."""
        mock_table = AsyncMock()
        mock_entity = {"RequestCount": 5}
        mock_table.get_entity = AsyncMock(return_value=mock_entity)
        tracker._table = mock_table
        
        with patch.object(tracker._settings, 'daily_request_limit', 20):
            used, remaining = await tracker.get_remaining(test_fingerprint)
        
        assert used == 5
        assert remaining == 15


@pytest.mark.unit
class TestCheckQuota:
    """Tests for check_quota method."""
    
    @pytest.mark.asyncio
    async def test_check_quota_allows_within_limit(self, tracker, test_fingerprint):
        """Test check_quota allows requests within limit."""
        mock_table = AsyncMock()
        mock_entity = {"RequestCount": 3}
        mock_table.get_entity = AsyncMock(return_value=mock_entity)
        tracker._table = mock_table
        
        allowed, used, remaining = await tracker.check_quota(test_fingerprint, limit=10)
        
        assert allowed is True
        assert used == 3
        assert remaining == 7
    
    @pytest.mark.asyncio
    async def test_check_quota_blocks_over_limit(self, tracker, test_fingerprint):
        """Test check_quota blocks requests over limit."""
        mock_table = AsyncMock()
        mock_entity = {"RequestCount": 10}
        mock_table.get_entity = AsyncMock(return_value=mock_entity)
        tracker._table = mock_table
        
        allowed, used, remaining = await tracker.check_quota(test_fingerprint, limit=10)
        
        assert allowed is False
        assert used == 10
        assert remaining == 0
    
    @pytest.mark.asyncio
    async def test_check_quota_remaining_never_negative(self, tracker, test_fingerprint):
        """Test remaining quota never goes below 0."""
        mock_table = AsyncMock()
        mock_entity = {"RequestCount": 15}
        mock_table.get_entity = AsyncMock(return_value=mock_entity)
        tracker._table = mock_table
        
        allowed, used, remaining = await tracker.check_quota(test_fingerprint, limit=10)
        
        assert remaining == 0
        assert allowed is False


@pytest.mark.unit
class TestListAllUsage:
    """Tests for list_all_usage method."""
    
    @pytest.mark.asyncio
    async def test_list_all_usage_returns_formatted_records(self, tracker):
        """Test list_all_usage returns formatted records."""
        mock_table = AsyncMock()
        
        # Create an async generator to return entities
        async def mock_list_entities():
            yield {
                "PartitionKey": "2024-01-01",
                "RowKey": "fp-1",
                "RequestCount": 5,
                "FirstRequestAt": "2024-01-01T10:00:00Z",
                "LastRequestAt": "2024-01-01T11:00:00Z",
                "UserAgent": "Mozilla/5.0",
                "IPAddress": "192.168.1.1",
                "Country": "US",
                "City": "San Francisco",
            }
        
        mock_table.list_entities = mock_list_entities
        tracker._table = mock_table
        
        records = await tracker.list_all_usage()
        
        assert len(records) == 1
        record = records[0]
        assert record["date"] == "2024-01-01"
        assert record["fingerprint"] == "fp-1"
        assert record["request_count"] == 5
        assert record["country"] == "US"
    
    @pytest.mark.asyncio
    async def test_list_all_usage_handles_missing_fields(self, tracker):
        """Test list_all_usage handles missing fields gracefully."""
        mock_table = AsyncMock()
        
        # Create an async generator to return entities
        async def mock_list_entities():
            yield {
                "PartitionKey": "2024-01-01",
                "RowKey": "fp-1",
                # Missing RequestCount, FirstRequestAt, etc.
            }
        
        mock_table.list_entities = mock_list_entities
        tracker._table = mock_table
        
        records = await tracker.list_all_usage()
        
        assert len(records) == 1
        assert records[0]["request_count"] == 0
        assert records[0]["country"] == ""


@pytest.mark.unit
class TestClose:
    """Tests for close method."""
    
    @pytest.mark.asyncio
    async def test_close_cleans_up_resources(self, tracker):
        """Test close method cleans up client and table."""
        mock_client = AsyncMock()
        tracker._client = mock_client
        tracker._table = AsyncMock()
        
        await tracker.close()
        
        assert tracker._client is None
        assert tracker._table is None
        mock_client.close.assert_called_once()


@pytest.mark.unit
class TestErrorHandling:
    """Tests for error handling."""
    
    @pytest.mark.asyncio
    async def test_get_usage_handles_unexpected_errors(self, tracker, test_fingerprint):
        """Test get_usage returns 0 on unexpected errors."""
        mock_table = AsyncMock()
        mock_table.get_entity = AsyncMock(side_effect=Exception("Unexpected error"))
        tracker._table = mock_table
        
        result = await tracker.get_usage(test_fingerprint)
        
        assert result == 0
    
    @pytest.mark.asyncio
    async def test_increment_usage_handles_update_errors(self, tracker, test_fingerprint):
        """Test increment_usage handles update errors gracefully."""
        mock_table = AsyncMock()
        mock_entity = {"RequestCount": 1}
        mock_table.get_entity = AsyncMock(return_value=mock_entity)
        mock_table.update_entity = AsyncMock(side_effect=Exception("Update failed"))
        tracker._table = mock_table
        
        with patch("app.services.geolocation.get_location_from_ip", new_callable=AsyncMock):
            # Should raise, as error handling depends on implementation
            with pytest.raises(Exception):
                await tracker.increment_usage(test_fingerprint)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
