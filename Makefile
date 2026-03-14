.PHONY: lint format test coverage

lint:
	ruff check src tests
	black --check src tests

format:
	ruff check --fix src tests
	black src tests

test:
	pytest

coverage:
	pytest --cov=src --cov-report=html --cov-fail-under=90
	@echo "Coverage report: htmlcov/index.html"
