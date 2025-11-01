# Development Guide

This guide is for developers working on the PDBe MCP Servers project.

## Table of Contents
- [Setup](#setup)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Code Quality](#code-quality)
- [Building and Distribution](#building-and-distribution)
- [Architecture](#architecture)

## Setup

### Prerequisites
- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

1. Clone the repository:
```bash
git clone https://github.com/PDBeurope/PDBe-MCP-Servers.git
cd PDBe-MCP-Servers
```

2. Set up development environment:
```bash
make dev-setup
# Or manually:
uv sync --all-extras --dev
```

## Development Workflow

### Quick Commands

The project includes a Makefile for common tasks:

```bash
make help          # Show all available commands
make install       # Install dependencies
make test          # Run tests with coverage
make lint          # Check code style
make format        # Format code
make typecheck     # Run type checker
make all           # Run all checks (lint, format, type, test)
```

### Manual Commands

If you prefer not to use Make:

```bash
# Install dependencies
uv sync --dev

# Run tests
uv run pytest

# Run linter
uv run ruff check .

# Format code
uv run ruff format .

# Type checking
uv run pyright
```

## Testing

### Running Tests

```bash
# All tests with coverage
make test

# Fast tests (no coverage)
make test-fast

# Specific test file
uv run pytest tests/test_utils.py

# Specific test class
uv run pytest tests/test_utils.py::TestHTMLStripper

# Specific test
uv run pytest tests/test_utils.py::TestHTMLStripper::test_strip_simple_tags

# With verbose output
uv run pytest -v

# Stop on first failure
uv run pytest -x
```

### Writing Tests

- Place tests in the `tests/` directory
- Name test files `test_*.py`
- Name test classes `Test*`
- Name test functions `test_*`
- Use fixtures from `conftest.py`
- Mock all external HTTP calls

Example test:

```python
from unittest.mock import MagicMock, patch

def test_example():
    """Test description."""
    # Arrange
    mock_data = {"key": "value"}

    # Act
    result = function_under_test(mock_data)

    # Assert
    assert result == expected_value
```

### Test Coverage

View coverage report:
```bash
make test
# Open htmlcov/index.html in browser
open htmlcov/index.html
```

Target: >80% coverage

## Code Quality

### Linting

The project uses Ruff for linting:

```bash
# Check for issues
make lint

# Fix auto-fixable issues
make lint-fix
```

### Formatting

The project uses Ruff for formatting:

```bash
# Format code
make format

# Check formatting without changing files
make format-check
```

### Type Checking

The project uses Pyright for type checking:

```bash
# Run type checker
make typecheck
```

All public APIs must have type annotations.

### Pre-commit Checks

Before committing, run:

```bash
make all
```

This runs linting, formatting checks, type checking, and tests.

## Building and Distribution

### Building the Package

```bash
# Build wheel and sdist
make build

# Check distribution files
make check-dist
```

### Publishing

```bash
# Test on TestPyPI first
make publish-test

# Publish to PyPI
make publish
```

## Architecture

### Project Structure

```
pdbe_mcp_server/
├── __init__.py          # Configuration management
├── api_tools.py         # OpenAPI to MCP tool conversion
├── config.yaml          # Configuration file
├── graph_tools.py       # Graph database tools
├── helper.py            # Helper utilities
├── py.typed             # PEP 561 marker
├── search_tools.py      # Search tools
├── server.py            # Server orchestration
└── utils.py             # Shared utilities

tests/
├── conftest.py          # Shared fixtures
├── test_api_tools.py    # API tools tests
├── test_graph_tools.py  # Graph tools tests
├── test_search_tools.py # Search tools tests
├── test_server.py       # Server tests
└── test_utils.py        # Utils tests
```

### Key Design Patterns

1. **Factory Pattern**: `MCPServerFactory` for creating servers
2. **Strategy Pattern**: Dynamic OpenAPI tool generation
3. **Adapter Pattern**: `HTTPClient` wrapper


### Adding a New Server Type

1. Create a builder function:
```python
def build_my_server() -> Server:
    server = Server("my-server")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [...]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> Sequence[...]:
        # Implementation
        pass

    return server
```

2. Register with factory:
```python
factory.register("my_server", build_my_server)
```

3. Update CLI options in `main()`.

### Adding Tests

1. Create test file in `tests/`
2. Add fixtures to `conftest.py` if reusable
3. Mock external dependencies
4. Test happy path and error cases

## Best Practices

### Code Style

- Use type hints for all public APIs
- Write docstrings for all public functions
- Use descriptive variable names
- Keep functions focused and small
- Prefer composition over inheritance

### Git Workflow

1. Create a feature branch
2. Make your changes
3. Run `make all` to check everything
4. Commit with descriptive message
5. Push and create pull request

### Commit Messages

Follow conventional commits:

```
feat: add new search filter option
fix: handle empty search results correctly
docs: update architecture documentation
test: add tests for graph tools
refactor: simplify server factory logic
```

## Troubleshooting

### Tests Failing

```bash
# Run with verbose output
uv run pytest -v

# Run single test to isolate issue
uv run pytest tests/test_utils.py::TestHTMLStripper::test_strip_simple_tags -v

# Check test isolation
uv run pytest --lf  # Run last failed
```

### Type Errors

```bash
# Run type checker with verbose output
uv run pyright --verbose

# Check specific file
uv run pyright pdbe_mcp_server/server.py
```

### Import Errors

```bash
# Reinstall dependencies
uv sync --reinstall

# Check installed packages
uv pip list
```

## Resources

- [Project README](README.md)
- [MCP Documentation](https://modelcontextprotocol.io/)
- [PDBe API](https://www.ebi.ac.uk/pdbe/api/)

## Contributing

1. Check existing issues/PRs
2. Create an issue for discussion (for large changes)
3. Fork and create a feature branch
4. Make your changes with tests
5. Ensure `make all` passes
6. Submit a pull request

## License

Apache-2.0 - See LICENSE file for details.
