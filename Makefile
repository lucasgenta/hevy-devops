# =============================================================================
# Hevy DevOps — Makefile
# =============================================================================
# Common targets for development, testing, and deployment.
#
# Usage:
#   make build    — Build all Docker images
#   make up       — Start all services in the background
#   make down     — Stop all services
#   make logs     — Tail logs from all services
#   make ps       — Show service status
#   make test     — Run CI checks locally (build + start + healthcheck)
#   make clean    — Remove volumes and reset state
#   make info     — Print deployment info
# =============================================================================

.PHONY: help build up down restart logs ps test clean info run-scrape

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: ## Build all Docker images (cached)
	docker compose build

build-no-cache: ## Build all Docker images (fresh)
	docker compose build --no-cache

up: ## Start all services in the background
	docker compose up -d

down: ## Stop all services (keeps volumes)
	docker compose down

restart: down up ## Restart all services

logs: ## Tail logs from all services
	docker compose logs -f

ps: ## Show service status
	docker compose ps

info: ## Print deployment information
	@echo "===== Hevy DevOps Stack ====="
	@echo "Gateway:   http://localhost"
	@echo "Dashboard: http://localhost (via gateway)"
	@echo "Health:    http://localhost/healthz"
	@echo ""
	@docker compose ps

run-scrape: ## Run the scraper once (manual trigger)
	docker compose run --rm -e SCRAPE_ONCE=1 scraper

test: ## Run CI checks locally (build, start, validate)
	@echo "===== Hevy DevOps — CI Check ====="
	@echo ""
	@echo "1. Building images..."
	@docker compose build
	@echo ""
	@echo "2. Starting services..."
	@docker compose up -d
	@echo ""
	@echo "3. Waiting for services to be healthy..."
	@sleep 15
	@echo ""
	@echo "4. Checking gateway health..."
	@if curl -sf http://localhost/healthz > /dev/null 2>&1; then \
		echo "   ✓ Gateway is healthy"; \
	else \
		echo "   ✗ Gateway is NOT healthy"; \
		docker compose logs --tail=20 gateway dashboard; \
		docker compose down; \
		exit 1; \
	fi
	@echo ""
	@echo "5. Checking service status..."
	@docker compose ps
	@echo ""
	@echo "6. Cleaning up..."
	@docker compose down
	@echo ""
	@echo "===== ✓ CI check passed ====="

clean: ## Remove volumes and reset state (WARNING: deletes data)
	docker compose down -v
	@echo "Volumes removed. All data wiped."

# ---- Advanced targets ----

scale: ## Scale dashboard replicas (usage: make scale N=3)
	@if [ -z "$(N)" ]; then echo "Usage: make scale N=3"; exit 1; fi
	docker compose up -d --scale dashboard=$(N)

shell-dashboard: ## Open a shell in the dashboard container
	docker compose exec dashboard /bin/sh

shell-scraper: ## Open a shell in the scraper container
	docker compose exec scraper /bin/sh

logs-dashboard: ## Tail dashboard logs
	docker compose logs -f dashboard

logs-scraper: ## Tail scraper logs
	docker compose logs -f scraper

logs-gateway: ## Tail gateway logs
	docker compose logs -f gateway
