# Test Suite for YouTube Monitoring Pipeline

## Overview

This directory contains the comprehensive test suite for the YouTube Monitoring Pipeline, organized into unit tests, integration tests, and end-to-end tests.

## Directory Structure

```
tests/
├── unit/                        # Fast, isolated unit tests
│   ├── test_helpers.py         # Utility function tests
│   └── test_database.py        # Database operation tests
├── integration/                 # Integration tests
│   └── test_api_mocked.py      # API client tests (mocked)
├── e2e/                        # End-to-end tests
│   └── test_collection_flow.py # Complete workflow tests
├── fixtures/                    # Test data and fixtures
├── conftest.py                 # Pytest configuration and shared fixtures
└── README.md                   # This file
```

## Running Tests

### Install Test Dependencies

```bash
pip install -r requirements.txt
# This installs pytest, pytest-cov, pytest-mock, pytest-timeout
```

### Run All Tests

```bash
pytest
```

### Run Specific Test Categories

```bash
# Run only unit tests (fast)
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run only e2e tests (slow)
pytest tests/e2e/

# Skip slow tests
pytest -m "not slow"

# Skip API tests (when no API key available)
pytest -m "not api"
```

### Run Specific Test Files

```bash
# Run helper tests
pytest tests/unit/test_helpers.py

# Run database tests
pytest tests/unit/test_database.py

# Run specific test
pytest tests/unit/test_helpers.py::TestExtractChannelId::test_extract_from_channel_url
```

### Run with Coverage

```bash
# Generate coverage report
pytest --cov=src --cov-report=html

# View coverage report
open htmlcov/index.html  # On macOS
# Or navigate to htmlcov/index.html in browser
```

### Run Tests in Parallel

```bash
# Install pytest-xdist first
pip install pytest-xdist

# Run tests in parallel
pytest -n auto
```

### Verbose Output

```bash
# Show more details
pytest -v

# Show local variables on failure
pytest -l

# Show print statements
pytest -s
```

## Test Markers

Tests are marked with decorators to categorize them:

- `@pytest.mark.unit` - Fast, isolated unit tests
- `@pytest.mark.integration` - Integration tests with multiple components
- `@pytest.mark.e2e` - End-to-end tests (slowest)
- `@pytest.mark.slow` - Tests that take > 1 second
- `@pytest.mark.api` - Tests requiring real API access
- `@pytest.mark.database` - Tests using database

### Using Markers

```bash
# Run only unit tests
pytest -m unit

# Run only fast tests
pytest -m "not slow"

# Run database tests
pytest -m database

# Run all except API tests
pytest -m "not api"
```

## Fixtures

Shared fixtures are defined in `conftest.py`:

### Database Fixtures
- `in_memory_db` - In-memory SQLite database
- `temp_db_file` - Temporary database file (cleaned up after test)
- `populated_db` - Database pre-populated with test data

### File System Fixtures
- `temp_dir` - Temporary directory
- `test_csv_file` - Sample CSV file with test channels
- `test_config_file` - Test configuration file

### API Response Fixtures
- `sample_channel_response` - Mock YouTube channel response
- `sample_video_response` - Mock YouTube video response
- `sample_comment_response` - Mock YouTube comment response
- `mock_youtube_client` - Fully mocked YouTube API client

## Writing New Tests

### Unit Test Example

```python
import pytest
from src.utils.helpers import format_duration

def test_format_duration():
    """Test duration formatting."""
    assert format_duration(90) == "1:30"
    assert format_duration(3600) == "1:00:00"
```

### Test with Fixture

```python
def test_database_insert(in_memory_db):
    """Test inserting data into database."""
    db = in_memory_db

    # Your test code here
    channel_data = {...}
    result = db.insert_channel(channel_data)

    assert result is True
```

### Parametrized Test

```python
@pytest.mark.parametrize("input,expected", [
    (60, "1:00"),
    (90, "1:30"),
    (3600, "1:00:00"),
])
def test_duration_formats(input, expected):
    assert format_duration(input) == expected
```

### Mocking External Calls

```python
from unittest.mock import patch

@patch('src.youtube_client.build')
def test_api_call(mock_build):
    """Test API call with mocked response."""
    mock_youtube = MagicMock()
    mock_build.return_value = mock_youtube

    # Configure mock
    mock_youtube.channels().list().execute.return_value = {...}

    # Test your code
    client = YouTubeAPIClient(api_key="test")
    result = client.get_channel_info("UC_test")

    assert result is not None
```

## Test Best Practices

1. **Test Naming**: Use descriptive names that explain what is being tested
   - `test_extract_channel_id_from_handle_url` ✅
   - `test_func1` ❌

2. **Arrange-Act-Assert**: Structure tests clearly
   ```python
   def test_something():
       # Arrange - set up test data
       data = {"key": "value"}

       # Act - perform the action
       result = process_data(data)

       # Assert - verify the result
       assert result == expected
   ```

3. **One Assertion Per Test**: Focus each test on one thing
   - Easier to debug when tests fail
   - More granular feedback

4. **Use Fixtures**: Don't repeat setup code
   - Define fixtures in `conftest.py`
   - Reuse across multiple tests

5. **Don't Test Implementation Details**: Test behavior, not internals

6. **Keep Tests Fast**: Unit tests should complete in < 100ms
   - Use mocking to avoid slow operations
   - Mark slow tests with `@pytest.mark.slow`

7. **Make Tests Independent**: Tests should not depend on each other
   - Each test should be able to run in isolation
   - Use fixtures for setup, not other tests

8. **Clean Up Resources**: Use fixtures with cleanup
   ```python
   @pytest.fixture
   def temp_file():
       f = create_temp_file()
       yield f
       f.cleanup()  # Cleanup after test
   ```

## Coverage Goals

| Component | Target Coverage |
|-----------|----------------|
| `src/utils/helpers.py` | 95%+ |
| `src/database.py` | 90%+ |
| `src/youtube_client.py` | 85%+ |
| Overall | 80%+ |

Check current coverage:
```bash
pytest --cov=src --cov-report=term-missing
```

## Continuous Integration

Tests run automatically on:
- Every push to branches
- Every pull request
- Before merging to `main` or `production`

### GitHub Actions Workflow

See `.github/workflows/tests.yml` (to be created) for CI configuration.

## Troubleshooting

### Tests Fail Locally

1. **Ensure dependencies are installed**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Activate virtual environment**:
   ```bash
   source venv/bin/activate
   ```

3. **Check Python version**:
   ```bash
   python --version  # Should be 3.8+
   ```

### Import Errors

If you see import errors:
```bash
# Ensure tests are run from project root
cd /path/to/youtube_monitoring_pipeline
pytest
```

### Database Errors

If database tests fail:
- Check SQLite is available: `python -c "import sqlite3; print('OK')"`
- Ensure temp directory is writable

### Slow Tests

Skip slow tests during development:
```bash
pytest -m "not slow"
```

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest Fixtures](https://docs.pytest.org/en/stable/fixture.html)
- [Unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
- [Testing Strategy](../TESTING_STRATEGY.md) - Full testing strategy document

## Contributing

When adding new features:
1. Write tests first (TDD)
2. Ensure tests pass: `pytest`
3. Check coverage: `pytest --cov=src`
4. Run specific test file: `pytest tests/unit/test_yourfile.py`
5. Commit tests with code changes

## Questions?

See [TESTING_STRATEGY.md](../TESTING_STRATEGY.md) for comprehensive testing guidelines.
