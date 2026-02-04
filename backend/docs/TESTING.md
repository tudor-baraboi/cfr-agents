# Backend Unit Testing - Getting Started

## Status: Phase 1 - Infrastructure & Auth Tests Complete ✅

**Created:** February 2, 2026

---

## What We've Built

### Test Infrastructure
- ✅ `pytest.ini` - Test configuration with async support and coverage
- ✅ `tests/conftest.py` - Shared fixtures for mocking Azure, APIs, JWT tokens
- ✅ `tests/unit/routers/test_auth.py` - 19 passing auth tests
- ✅ Test directory structure: `tests/unit/{routers,services,tools}/`

### Test Results (auth.py)
```
19 passed, 2 skipped (integration tests requiring Azure Tables)
Coverage: 70% of auth.py (88 lines)
Execution time: ~6 seconds
```

### Test Coverage Breakdown
**Fingerprint Authentication (7 tests):**
- ✅ New user authentication with quota tracking
- ✅ Existing user returns current usage stats
- ✅ Missing/empty/short visitor_id validation
- ✅ Valid long visitor_id success
- ⏭️ Quota exhausted scenario (skipped - needs Azure Tables integration)

**Admin Code Validation (5 tests):**
- ✅ Valid admin code success (unlimited access)
- ✅ Invalid code rejection
- ✅ Empty code rejection
- ✅ Fingerprint optional for admin
- ✅ Case-insensitive code matching (uppercased)

**JWT Token Tests (6 tests):**
- ✅ Token contains fingerprint
- ✅ Token contains is_admin flag
- ✅ Token has expiration and issued-at timestamps
- ✅ Expired token rejected
- ✅ Invalid/malformed token rejected
- ✅ Token with wrong secret rejected

**Integration Tests (3 tests):**
- ✅ Auth updates usage counter
- ✅ Admin bypasses quota limits
- ⏭️ Daily limit enforcement (skipped - needs Azure Tables)

---

## Test Dependencies

### Installed Packages
```bash
pytest>=8.0.0          # Core testing framework
pytest-asyncio>=0.24.0 # Async test support
pytest-cov>=4.1.0      # Code coverage reports
pytest-mock>=3.12.0    # Mocking utilities
respx>=0.20.0          # httpx mocking for API calls
faker>=22.0.0          # Test data generation
freezegun>=1.4.0       # Time/date freezing for tests
```

### Shared Fixtures (conftest.py)
- `client` - FastAPI TestClient
- `test_settings` - Test environment settings
- `mock_azure_blob` - Azure Blob Storage mock
- `mock_azure_table` - Azure Table Storage mock
- `mock_httpx_client` - External API call mocking
- `mock_claude_client` - Anthropic Claude API mock
- `valid_jwt_token` - Pre-generated valid JWT
- `admin_jwt_token` - Pre-generated admin JWT
- `expired_jwt_token` - Pre-generated expired JWT
- `sample_usage_entity` - Mock usage data from Tables
- `sample_pdf_bytes` - Minimal valid PDF for testing

---

## Running Tests

### Run All Auth Tests
```bash
cd backend
python3 -m pytest tests/unit/routers/test_auth.py -v
```

### Run with Coverage Report
```bash
python3 -m pytest tests/unit/routers/test_auth.py --cov=app.routers.auth --cov-report=term-missing
```

### Run Specific Test
```bash
python3 -m pytest tests/unit/routers/test_auth.py::TestFingerprintAuth::test_fingerprint_auth_new_user -v
```

### Run Only Unit Tests (Skip Integration)
```bash
python3 -m pytest tests/unit/routers/test_auth.py -m unit -v
```

---

## Next Steps: Implementing More Tests

### Phase 1 Priority (Security & Core - 2 weeks)
**Routers:**
- [ ] `main.py` - WebSocket endpoint tests (~15 tests)
  - Connection/disconnection
  - Message streaming
  - Error handling
  - Rate limiting
  
- [ ] `documents.py` - PDF upload tests (~20 tests)
  - Text PDF extraction
  - OCR fallback for scanned PDFs
  - File size limits
  - Duplicate detection
  - Embedding generation failures

**Services:**
- [ ] `orchestrator.py` - Tool calling tests (~25 tests)
  - Simple responses without tools
  - Single tool calls
  - Multiple tool calls
  - Streaming interruption
  - Token limits
  - Retry logic
  - Extended Thinking blocks
  
- [ ] `usage.py` - Quota tracking tests (~15 tests)
  - Daily quota checking
  - Quota reset at midnight UTC
  - Usage incrementing
  - Admin unlimited access
  - Geolocation tracking

**Tools (Critical):**
- [ ] `fetch_cfr.py` - CFR fetching tests (~15 tests)
  - Cache hit/miss
  - eCFR API 404 handling
  - XML parsing
  - Subsection extraction
  - Auto-indexing
  
- [ ] `drs.py` - DRS API tests (~20 tests)
  - Search with filters
  - Pagination
  - Document download
  - API key validation
  - Empty results

### Phase 2 Priority (Document Pipeline - 2 weeks)
- [ ] `indexer.py` - Embedding generation (~15 tests)
- [ ] `search_indexed.py` - Vector search (~12 tests)
- [ ] `tools/documents.py` - Document tool tests (~18 tests)
- [ ] `cache.py` - Blob cache tests (~15 tests)
- [ ] `search_proxy` - Document isolation tests (~20 tests)

### Phase 3 Priority (Complete Coverage - 2 weeks)
- [ ] `tools/aps.py` - NRC ADAMS API tests (~15 tests)
- [ ] `feedback.py` router & service (~15 tests)
- [ ] `conversation.py` - History management (~8 tests)
- [ ] `geolocation.py` - IP lookup tests (~10 tests)
- [ ] `admin.py` - Admin endpoints (~8 tests)
- [ ] Integration tests - End-to-end flows (~20 tests)

---

## Testing Best Practices

### 1. Async Testing
```python
@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result == expected
```

### 2. Mocking External Dependencies
```python
@patch("httpx.AsyncClient")
def test_external_api(mock_httpx):
    mock_response = AsyncMock()
    mock_response.json.return_value = {"data": "test"}
    mock_httpx.return_value.get.return_value = mock_response
    # ... test code
```

### 3. Fixture Reuse
```python
def test_with_shared_fixtures(client, valid_jwt_token):
    response = client.get(
        "/protected-endpoint",
        headers={"Authorization": f"Bearer {valid_jwt_token}"}
    )
    assert response.status_code == 200
```

### 4. Parameterized Tests
```python
@pytest.mark.parametrize("visitor_id,expected_status", [
    ("valid-id-12345", 200),
    ("short", 400),
    ("", 400),
])
def test_visitor_id_validation(client, visitor_id, expected_status):
    response = client.post("/auth/fingerprint", json={"visitor_id": visitor_id})
    assert response.status_code == expected_status
```

---

## Current Test Coverage

### Overall Backend Coverage: 21%
```
app/routers/auth.py         70% coverage (21/88 lines missed)
app/routers/health.py       75% coverage
app/routers/admin.py        60% coverage
app/routers/documents.py    18% coverage (needs tests)
app/routers/feedback.py     44% coverage (needs tests)
app/main.py                 17% coverage (needs tests)
app/services/*              5-48% coverage (all need tests)
app/tools/*                 7-48% coverage (all need tests)
```

### Target Coverage Goals
- **Critical modules:** 85%+ (auth, main, orchestrator, usage)
- **High-priority:** 75%+ (tools, indexer, documents)
- **Medium-priority:** 65%+ (cache, feedback, admin)
- **Overall backend:** 70%+

---

## Troubleshooting

### "Event loop is closed" Error
- Ensure `pytest-asyncio` is installed
- Check `pytest.ini` has `asyncio_mode = auto`
- Verify fixtures use `async def` when calling async code

### Mocks Not Working
- Import mocks before the module under test
- Use `AsyncMock()` for async functions
- Patch at the usage location, not definition: `@patch("app.routers.auth.get_usage_tracker")`

### Coverage Not Showing
- Run with `--cov=app` flag
- Check `pytest.ini` has coverage configured
- Generate HTML report: `--cov-report=html`

### Tests Slow
- Use `pytest-xdist` for parallel execution: `pytest -n auto`
- Mock external API calls properly
- Skip slow integration tests: `pytest -m "not slow"`

---

## Resources

- **Pytest Docs:** https://docs.pytest.org/
- **Pytest-asyncio:** https://pytest-asyncio.readthedocs.io/
- **Respx (httpx mocking):** https://lundberg.github.io/respx/
- **Coverage.py:** https://coverage.readthedocs.io/

---

## Test Statistics

**As of February 2, 2026:**
- Total tests written: 19 (2 skipped)
- Tests passing: 19
- Code coverage gained: +21% (from 0%)
- Modules with tests: 1/26 (auth.py)
- Estimated remaining tests: ~430-480

**Time investment:**
- Infrastructure setup: ~1 hour
- Auth tests: ~1.5 hours
- Total: 2.5 hours

**Next milestone:** 
Main.py WebSocket tests + Orchestrator tool calling tests (~40 more tests, ~3 hours)
