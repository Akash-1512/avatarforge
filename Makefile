.PHONY: dev down test lint format build clean logs smoke

dev:            ## Start full stack (api, worker, flower, postgres, redis)
	docker compose up --build -d
	@echo "API:    http://localhost:8000/docs"
	@echo "Flower: http://localhost:5555"

down:           ## Stop all containers
	docker compose down

test:           ## Run unit tests with coverage (inside the api container)
	docker compose run --rm --no-deps api python -m pytest backend/tests/ -v --cov=backend --cov-report=term-missing

models:         ## Download SadTalker checkpoints (~4GB, one-time)
	docker compose run --rm sadtalker python download_models.py

eval:           ## Run the script-generation eval harness (regression gate)
	docker compose run --rm --no-deps api python -m backend.evals.runner $(EVAL_ARGS)

migrate:        ## Apply database migrations
	docker compose run --rm --no-deps --entrypoint "" api sh -c 'cd /app/backend && alembic upgrade head'

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
