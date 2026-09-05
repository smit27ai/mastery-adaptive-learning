.DEFAULT_GOAL := help
PY := python

.PHONY: help setup seed serve dashboard web web-install web-build verify test lint fmt typecheck check docker-build docker-up docker-down migrate clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Create the virtualenv and install everything
	$(PY) -m venv .venv
	.venv/Scripts/python -m pip install --upgrade pip || .venv/bin/python -m pip install --upgrade pip
	.venv/Scripts/pip install -e ".[dev,dashboard]" || .venv/bin/pip install -e ".[dev,dashboard]"
	@echo "Done. Copy .env.example to .env, then run: make seed && make serve"

seed: ## Load the demo curriculum and demo users
	$(PY) -m mastery.data.seed

serve: ## Run the API with hot reload on http://localhost:8000
	uvicorn mastery.api.main:app --reload --host 0.0.0.0 --port 8000

dashboard: ## Run the instructor dashboard on http://localhost:8501
	streamlit run src/mastery/dashboard/app.py

web-install: ## Install the student app's dependencies
	cd web && npm install

web: ## Run the student app on http://localhost:3000
	cd web && npm run dev

web-build: ## Production build of the student app (typechecks too)
	cd web && npm run typecheck && npm run build

verify: ## Check a live deployment: make verify URL=https://... [ORIGIN=https://...]
	$(PY) scripts/verify_deployment.py $(URL) $(if $(ORIGIN),--origin $(ORIGIN),)

test: ## Run the test suite with coverage
	pytest --cov=mastery --cov-report=term-missing

lint: ## Ruff
	ruff check src tests

fmt: ## Format with black and autofix with ruff
	black src tests
	ruff check --fix src tests

typecheck: ## Mypy
	mypy src

check: lint typecheck test ## Everything CI runs

docker-build: ## Build the production image
	docker build -t mastery:local .

docker-up: ## Full stack: Postgres + Redis + API
	docker compose up --build

docker-down: ## Tear the stack down
	docker compose down -v

migrate: ## Apply database migrations
	alembic upgrade head

clean: ## Remove caches and the local database
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage mastery.db
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
