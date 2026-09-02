# Convenience wrapper around the documented commands. Every target here maps to
# something CI also runs, so "green locally" and "green in CI" mean the same.

COMPOSE ?= docker compose
BACKEND  = $(COMPOSE) exec backend
FRONTEND = $(COMPOSE) exec frontend

.DEFAULT_GOAL := help
.PHONY: help setup up down logs ps restart shell dbshell migrate makemigrations \
        superuser seed seed-courses seed-batches seed-all test test-backend test-frontend test-e2e lint lint-backend \
        lint-frontend format typecheck security check build clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: ## First-time setup: create .env from the template
	@test -f .env || (cp .env.example .env && echo "Created .env — fill in POSTGRES_PASSWORD before starting.")

up: ## Start the stack (build if needed)
	$(COMPOSE) up --build -d
	@echo "Backend  http://localhost:$${BACKEND_PORT:-8000}"
	@echo "Frontend http://localhost:$${FRONTEND_PORT:-3000}"

down: ## Stop the stack (keeps data)
	$(COMPOSE) down

clean: ## Stop the stack and delete all volumes (DESTROYS LOCAL DATA)
	$(COMPOSE) down -v

logs: ## Follow logs
	$(COMPOSE) logs -f

ps: ## Show service status
	$(COMPOSE) ps

restart: ## Restart the backend
	$(COMPOSE) restart backend

shell: ## Django shell
	$(BACKEND) python manage.py shell

dbshell: ## PostgreSQL shell
	$(BACKEND) python manage.py dbshell

migrate: ## Apply migrations
	$(BACKEND) python manage.py migrate

makemigrations: ## Create migrations
	$(BACKEND) python manage.py makemigrations

superuser: ## Create an administrator account
	$(BACKEND) python manage.py createsuperuser

seed: ## Create fake demo users and profiles (needs DEMO_USER_PASSWORD)
	$(BACKEND) python manage.py seed_demo_data

seed-courses: ## Create fake course catalogue data (run `make seed` first)
	$(BACKEND) python manage.py seed_courses --with-files

seed-batches: ## Create fake batches and enrolments (run `make seed-courses` first)
	$(BACKEND) python manage.py seed_batches

seed-all: seed seed-courses seed-batches ## Seed everything, in order

test: test-backend test-frontend ## Run backend and frontend test suites

test-backend: ## Backend tests with coverage
	$(BACKEND) pytest --cov --cov-report=term-missing

test-frontend: ## Frontend unit tests
	$(FRONTEND) npm test

test-e2e: ## End-to-end tests against the running stack (needs seeded data)
	cd frontend && E2E_BASE_URL=http://localhost:$${FRONTEND_PORT:-3000} \
		E2E_DEMO_PASSWORD=$${DEMO_USER_PASSWORD} npx playwright test

lint: lint-backend lint-frontend ## Lint everything

lint-backend: ## Ruff format check + lint
	$(BACKEND) ruff format --check .
	$(BACKEND) ruff check .

lint-frontend: ## ESLint
	$(FRONTEND) npm run lint

format: ## Auto-format the backend
	$(BACKEND) ruff format .
	$(BACKEND) ruff check --fix .

typecheck: ## Frontend type checking
	$(FRONTEND) npm run typecheck

security: ## SAST + dependency vulnerability scans
	$(BACKEND) bandit -c pyproject.toml -r apps config manage.py
	$(BACKEND) pip-audit -r requirements/dev.txt --strict
	$(FRONTEND) npm audit --audit-level=high

check: ## Django deployment checks against production settings
	$(BACKEND) sh -c 'DJANGO_ENV=production DJANGO_SETTINGS_MODULE=config.settings.production \
		DJANGO_SECRET_KEY=$${DJANGO_SECRET_KEY:-check-only-Kd83nfL2pQx7ZmVt5RwYbHcE9sJaU4gT6iOzXqNyBvMlPr} \
		DJANGO_ALLOWED_HOSTS=api.example.com \
		CSRF_TRUSTED_ORIGINS=https://app.example.com \
		CORS_ALLOWED_ORIGINS=https://app.example.com \
		DATABASE_URL=postgres://u:p@db.example.com:5432/lms \
		CACHE_URL=redis://cache.example.com:6379/0 \
		EMAIL_HOST=smtp.example.com \
		DEFAULT_FROM_EMAIL=no-reply@example.com \
		FRONTEND_BASE_URL=https://app.example.com \
		python manage.py check --deploy --fail-level WARNING'

build: ## Build production images
	docker build -f infra/docker/backend.Dockerfile --target production -t grras-lms-backend:local .
	docker build -f infra/docker/frontend.Dockerfile --target production -t grras-lms-frontend:local .
