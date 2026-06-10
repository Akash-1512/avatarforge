.PHONY: dev down test lint format build clean logs smoke

dev:            ## Start full stack (api, worker, flower, postgres, redis)
	docker compose up --build -d
	@echo "API:    http://localhost:8000/docs"
	@echo "Flower: http://localhost:5555"

down:           ## Stop all containers
	docker compose down

test:           ## Run unit tests with coverage
	cd backend && python -m pytest tests/ -v --cov=. --cov-report=term-missing

lint:           ## Run all linters
	cd backend && black --check . && isort --check-only . && flake8 . && mypy . --ignore-missing-imports

format:         ## Auto-format code
	cd backend && black . && isort .

build:          ## Build images without starting
	docker compose build

logs:           ## Tail logs from all services
	docker compose logs -f

smoke:          ## Fire the Celery smoke task and verify round-trip
	docker compose exec api python -c "from backend.workers.tasks import ping; r = ping.delay('phase1'); print(r.get(timeout=10))"

clean:          ## Remove containers, volumes, caches
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
