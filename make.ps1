# avatarforge task runner for Windows PowerShell
# Usage:  .\make.ps1 dev   |   .\make.ps1 test   |   .\make.ps1 smoke   etc.

param(
    [Parameter(Position = 0)]
    [ValidateSet("dev", "down", "test", "lint", "format", "build", "logs", "smoke", "clean", "help")]
    [string]$Task = "help"
)

switch ($Task) {
    "dev" {
        docker compose up --build -d
        Write-Host ""
        Write-Host "API:    http://localhost:8000/docs" -ForegroundColor Green
        Write-Host "Flower: http://localhost:5555" -ForegroundColor Green
    }
    "down" {
        docker compose down
    }
    "test" {
        Push-Location backend
        python -m pytest tests/ -v --cov=. --cov-report=term-missing
        Pop-Location
    }
    "lint" {
        Push-Location backend
        black --check .
        isort --check-only .
        flake8 .
        mypy . --ignore-missing-imports
        Pop-Location
    }
    "format" {
        Push-Location backend
        black .
        isort .
        Pop-Location
    }
    "build" {
        docker compose build
    }
    "logs" {
        docker compose logs -f
    }
    "smoke" {
        docker compose exec api python -c "from backend.workers.tasks import ping; r = ping.delay('phase1'); print(r.get(timeout=10))"
    }
    "clean" {
        docker compose down -v
        Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
    "help" {
        Write-Host "avatarforge tasks:" -ForegroundColor Cyan
        Write-Host "  .\make.ps1 dev      Start full stack (api, worker, flower, postgres, redis)"
        Write-Host "  .\make.ps1 down     Stop all containers"
        Write-Host "  .\make.ps1 test     Run unit tests with coverage"
        Write-Host "  .\make.ps1 lint     Run all linters"
        Write-Host "  .\make.ps1 format   Auto-format code"
        Write-Host "  .\make.ps1 build    Build images without starting"
        Write-Host "  .\make.ps1 logs     Tail logs from all services"
        Write-Host "  .\make.ps1 smoke    Fire the Celery smoke task"
        Write-Host "  .\make.ps1 clean    Remove containers, volumes, caches"
    }
}
