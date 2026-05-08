# Convenience targets for common dev tasks.
# Run with `make <target>`.

.PHONY: help install init-db seed-demo run test lint typecheck clean

help:  ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?##"}; {printf "  \033[1m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install runtime + dev dependencies.
	pip install -r requirements-dev.txt

init-db:  ## Create tables and seed task types.
	flask --app app.py init-db

seed-demo:  ## Drop and recreate the demo user with realistic data.
	flask --app app.py seed-demo

run:  ## Start the Flask development server on port 5050.
	flask --app app.py run --debug --port 5050

test:  ## Run the pytest suite.
	python -m pytest tests/

lint:  ## Static-analysis pass with ruff.
	ruff check stride/ app.py config.py tests/

typecheck:  ## Static type-check with mypy.
	python -m mypy stride/

clean:  ## Remove caches, pickled models, and the SQLite database.
	rm -rf .pytest_cache __pycache__ stride/__pycache__ stride/**/__pycache__
	rm -f instance/stride.db instance/model_*.pkl
