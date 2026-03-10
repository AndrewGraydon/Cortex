.PHONY: dev install lint format test test-hw test-all test-fault test-soak backup restore clean

# Development setup
dev:
	python -m venv .venv
	.venv/bin/pip install -e ".[dev]"
	.venv/bin/pre-commit install
	@echo "✓ Dev environment ready. Activate with: source .venv/bin/activate"

# Install (production)
install:
	pip install -e .

# Linting and formatting
lint:
	ruff check src/ tests/
	ruff format --check src/ tests/
	mypy src/

format:
	ruff check --fix src/ tests/
	ruff format src/ tests/

# Tests
test:
	pytest -m "not hardware and not soak" --tb=short -q

test-hw:
	pytest -m "hardware" --tb=short -q

test-all:
	pytest --tb=short

test-cov:
	pytest -m "not hardware and not soak" --cov=cortex --cov-report=term-missing --tb=short

test-fault:
	pytest tests/soak/test_fault_injection.py -v --tb=short

test-soak:
	SOAK_DRY_RUN=1 pytest tests/soak/test_soak_24h.py -m soak -v --tb=short

# Backup and restore
backup:
	bash scripts/backup.sh

restore:
	bash scripts/restore.sh

# Cleanup
clean:
	rm -rf .venv build dist *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
