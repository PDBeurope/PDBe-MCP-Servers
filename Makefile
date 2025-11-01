.PHONY: help install test lint format typecheck clean build docs all

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install package and dependencies
	uv sync --all-extras --dev

test: ## Run tests with coverage
	uv run pytest --cov=pdbe_mcp_server --cov-report=term-missing --cov-report=html

test-fast: ## Run tests without coverage
	uv run pytest -v

test-watch: ## Run tests in watch mode
	uv run pytest-watch

lint: ## Run linter
	uv run ruff check .

lint-fix: ## Run linter and fix issues
	uv run ruff check --fix .

format: ## Format code
	uv run ruff format .

format-check: ## Check code formatting without changing files
	uv run ruff format --check .

typecheck: ## Run type checker
	uv run pyright

clean: ## Clean build artifacts and cache
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build: clean ## Build package
	uv build

check-dist: build ## Check distribution files
	uv run twine check dist/*

publish-test: check-dist ## Publish to TestPyPI
	uv run twine upload --repository testpypi dist/*

publish: check-dist ## Publish to PyPI
	uv run twine upload dist/*

docs: ## Generate documentation (placeholder)
	@echo "Documentation generation not yet implemented"

all: lint format-check typecheck test ## Run all checks

ci: install all build ## Run all CI checks

dev-setup: install ## Set up development environment
	@echo "Development environment set up successfully!"
	@echo "Run 'make test' to run tests"
	@echo "Run 'make help' to see all available commands"
