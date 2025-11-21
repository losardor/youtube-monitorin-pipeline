# Testing Strategy for YouTube Monitoring Pipeline

## Overview

This document outlines the comprehensive testing strategy for the YouTube Monitoring Pipeline, covering unit tests, integration tests, and end-to-end tests.

## Testing Philosophy

1. **Test Pyramid**: Follow the testing pyramid with more unit tests than integration tests, and fewer end-to-end tests
2. **Fast Feedback**: Tests should run quickly to enable rapid development
3. **Isolation**: Each test should be independent and not rely on external state
4. **Coverage**: Aim for 80%+ code coverage on critical paths
5. **API Quota Protection**: Mock API calls to avoid consuming quota during testing

## Component Testing Breakdown

### 1. Unit Tests (Fast, Isolated)

Test individual functions and methods in isolation.

#### 1.1 Utility Functions (`src/utils/helpers.py`)
**What to test:**
- ✅ `extract_channel_id_from_url()` - Various URL formats
- ✅ `format_duration()` - Edge cases (0, negative, large numbers)
- ✅ `clean_text()` - Whitespace, special characters, empty strings
- ✅ `calculate_engagement_rate()` - Division by zero, missing data
- ✅ `categorize_video_length()` - Boundary values
- ✅ `save_json()` / `load_json()` - File I/O, error handling

**Test categories:**
- Happy path (expected inputs)
- Edge cases (boundary values, empty inputs)
- Error cases (invalid inputs, exceptions)

#### 1.2 Database Operations (`src/database.py`)
**What to test:**
- ✅ Table creation and schema validation
- ✅ Insert operations (channels, videos, comments)
- ✅ Upsert behavior (INSERT OR REPLACE)
- ✅ Foreign key constraints
- ✅ Query operations
- ✅ Transaction handling

**Testing approach:**
- Use in-memory SQLite database (`:memory:`)
- Test data fixtures for consistency
- Verify data integrity and constraints

#### 1.3 YouTube Client (`src/youtube_client.py`)
**What to test (with mocking):**
- ✅ Channel ID extraction from various URL formats
- ✅ API request construction
- ✅ Response parsing
- ✅ Retry logic on failures
- ✅ Quota tracking
- ✅ Error handling (404, 403, network errors)

**Mocking strategy:**
- Mock `googleapiclient` to avoid real API calls
- Use fixtures with sample API responses
- Test rate limiting without delays

### 2. Integration Tests (Medium Speed)

Test interactions between components.

#### 2.1 Database Integration
**What to test:**
- ✅ Full data flow: Channel → Videos → Comments
- ✅ Checkpoint save/restore functionality
- ✅ CSV export functionality
- ✅ Data consistency across tables
- ✅ Query performance with realistic data volumes

**Setup:**
- Use temporary SQLite file
- Seed with realistic test data
- Clean up after tests

#### 2.2 API Client Integration (with real API)
**What to test:**
- ✅ Real API connection (use separate test API key)
- ✅ Rate limiting behavior
- ✅ Pagination handling
- ✅ Error recovery from API failures

**Prerequisites:**
- Separate test API key with low quota
- Test against well-known stable channels
- Skip if API key not available (optional tests)

### 3. End-to-End Tests (Slow)

Test complete workflows from start to finish.

#### 3.1 Collection Workflow
**What to test:**
- ✅ Full collection cycle with 1-2 channels
- ✅ Resume from checkpoint
- ✅ Error handling with failed channels
- ✅ Data consistency after collection
- ✅ Log file generation

**Setup:**
- Use test configuration file
- Small test CSV with 2-3 channels
- Separate test database

#### 3.2 Data Export Workflow
**What to test:**
- ✅ Database → CSV export
- ✅ Data integrity during export
- ✅ Handle large datasets

### 4. System/Smoke Tests

Quick validation that the system is functional.

#### 4.1 Configuration Tests
- ✅ Config file loading
- ✅ API key validation
- ✅ Required directories exist

#### 4.2 CLI Tests
- ✅ Command-line argument parsing
- ✅ Help text display
- ✅ Error messages for missing arguments

## Test Organization

```
tests/
├── unit/
│   ├── test_helpers.py          # Utility function tests
│   ├── test_database.py         # Database operation tests
│   └── test_youtube_client.py   # API client tests (mocked)
├── integration/
│   ├── test_database_integration.py
│   ├── test_api_integration.py  # Real API tests (optional)
│   └── test_checkpoint.py
├── e2e/
│   ├── test_collection_flow.py
│   └── test_export_flow.py
├── fixtures/
│   ├── sample_api_responses.json
│   ├── test_channels.csv
│   └── test_config.yaml
├── conftest.py                  # Pytest fixtures and configuration
└── __init__.py
```

## Test Data Strategy

### Fixtures
1. **Sample API Responses**: JSON files with realistic YouTube API responses
2. **Test CSV**: Small CSV with 5-10 test channels
3. **Test Configuration**: Config with safe settings for testing
4. **Mock Database**: Seed data for database tests

### Test Channels
Use stable, public channels for testing:
- Large channel (1M+ subscribers)
- Medium channel (100k subscribers)
- Small channel (<10k subscribers)
- Channel with disabled comments
- Channel with various video types

## Mocking Strategy

### What to Mock
1. **YouTube API calls**: Always mock in unit/integration tests
2. **File I/O**: Mock when testing logic, not when testing file operations
3. **Time/dates**: Mock for consistent test results
4. **Network requests**: Mock to avoid external dependencies

### What NOT to Mock
1. **Database operations in integration tests**: Use real SQLite
2. **Configuration parsing**: Test real YAML loading
3. **Data transformations**: Test actual logic

## Test Tools and Libraries

### Required
- `pytest` - Test framework
- `pytest-cov` - Coverage reporting
- `pytest-mock` - Mocking utilities
- `unittest.mock` - Python standard mocking

### Optional
- `pytest-xdist` - Parallel test execution
- `pytest-timeout` - Prevent hanging tests
- `freezegun` - Mock datetime
- `responses` - Mock HTTP requests
- `faker` - Generate test data

## Running Tests

### Basic Commands
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test category
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/

# Run specific test file
pytest tests/unit/test_helpers.py

# Run specific test
pytest tests/unit/test_helpers.py::test_extract_channel_id_from_url

# Run with verbose output
pytest -v

# Run in parallel (faster)
pytest -n auto
```

### Test Markers
```bash
# Skip slow tests
pytest -m "not slow"

# Run only integration tests
pytest -m integration

# Skip API tests (when no API key)
pytest -m "not api"
```

## Continuous Integration

### GitHub Actions Workflow
```yaml
# Run on every PR and push to main/production
- Run unit tests (always)
- Run integration tests (always)
- Run e2e tests (only on main/production)
- Generate coverage report
- Fail if coverage < 80%
```

### Pre-commit Hooks
- Run fast unit tests before commit
- Check code formatting
- Lint with `pylint` or `flake8`

## Coverage Goals

| Component | Target Coverage |
|-----------|----------------|
| `src/utils/helpers.py` | 95%+ |
| `src/database.py` | 90%+ |
| `src/youtube_client.py` | 85%+ |
| `collect.py` | 70%+ |
| Overall | 80%+ |

## Test Maintenance

### Guidelines
1. **Update tests with code changes**: Keep tests in sync with implementation
2. **Review test failures**: Don't ignore failing tests
3. **Refactor tests**: Remove duplicate code, use fixtures
4. **Document complex tests**: Add comments explaining "why"
5. **Regular cleanup**: Remove obsolete tests

### Test Smells to Avoid
- ❌ Tests that depend on execution order
- ❌ Tests that require manual setup
- ❌ Tests that fail intermittently
- ❌ Tests that take > 1 second (unit tests)
- ❌ Tests that use production data
- ❌ Tests that consume API quota

## Performance Testing

### Load Tests
- Test with 1000+ channels in database
- Verify query performance
- Check memory usage during collection
- Profile slow operations

### Stress Tests
- Maximum concurrent database connections
- Large batch inserts (10k+ comments)
- Rapid API pagination

## Security Testing

### What to Test
- ✅ No API keys in logs
- ✅ SQL injection protection (parameterized queries)
- ✅ File path traversal protection
- ✅ Input validation on user-provided data

## Error Scenario Testing

### Network Failures
- API timeout
- Connection reset
- DNS failure

### API Errors
- 403 Quota exceeded
- 404 Channel not found
- 500 Server error
- Invalid API key

### Data Errors
- Malformed CSV
- Invalid channel URLs
- Missing required fields
- Corrupted database

## Test Documentation

Each test should include:
1. **Docstring**: Brief description of what is tested
2. **Given-When-Then**: Structure test clearly
3. **Assertions**: Meaningful assertion messages
4. **Edge cases**: Document non-obvious test cases

Example:
```python
def test_extract_channel_id_from_handle_url():
    """Test channel ID extraction from @handle format URLs.

    Given: A YouTube URL with @handle format
    When: extract_channel_id_from_url is called
    Then: Returns the handle with @ prefix
    """
    url = "https://www.youtube.com/@testchannel"
    result = extract_channel_id_from_url(url)
    assert result == "@testchannel", "Should extract handle with @ prefix"
```

## Monitoring Test Health

### Metrics to Track
- Test execution time (should decrease over time)
- Test coverage percentage
- Number of flaky tests
- Time to fix broken tests
- Number of skipped tests

### Test Reports
- Generate HTML coverage reports
- Track trends over time
- Share results with team

## Special Considerations

### Testing with Real API
- Use separate test API key
- Limit to 1-2 channels
- Mark as `@pytest.mark.api`
- Make optional (skip if no key)

### Testing Database Migrations
- Test schema changes
- Verify data preservation
- Test rollback capability

### Testing Checkpoints
- Verify checkpoint save
- Test resume functionality
- Handle corrupted checkpoints

## Next Steps

1. ✅ Set up pytest infrastructure
2. ✅ Create test fixtures and sample data
3. ✅ Implement unit tests for utilities
4. ✅ Implement database tests
5. ✅ Implement API client tests (mocked)
6. ✅ Add integration tests
7. ✅ Add end-to-end tests
8. ✅ Set up CI/CD pipeline
9. ✅ Generate coverage reports
10. ✅ Document test procedures

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Python Testing Best Practices](https://realpython.com/python-testing/)
- [Mock Documentation](https://docs.python.org/3/library/unittest.mock.html)
- YouTube Data API [Testing Guide](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits)
