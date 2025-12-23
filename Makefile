# Agent Service Makefile
# Usage: make <target>

.PHONY: help install install-dev test lint format run docker-build docker-up docker-down docker-logs clean

# Default target
help:
	@echo "Agent Service - Available Commands"
	@echo "==================================="
	@echo "  make install      Install production dependencies"
	@echo "  make install-dev  Install dev dependencies (includes ruff)"
	@echo "  make test         Run tests with pytest"
	@echo "  make lint         Run ruff linter"
	@echo "  make format       Format code with ruff"
	@echo "  make run          Run local dev server"
	@echo "  make docker-build Build Docker image"
	@echo "  make docker-up    Start with docker-compose"
	@echo "  make docker-down  Stop docker-compose"
	@echo "  make docker-logs  View container logs"
	@echo "  make clean        Remove cache files"

# =============================================================================
# Development
# =============================================================================

install:
	pip install -r requirements.txt

install-dev: install
	pip install -r requirements-dev.txt

test:
	python -m pytest tests/ -v

test-quick:
	python -m pytest tests/ -q

lint:
	ruff check .

format:
	ruff format .
	ruff check --fix .

run:
	uvicorn main:app --reload --host 127.0.0.1 --port 8000

# =============================================================================
# Docker
# =============================================================================

docker-build:
	docker build -t agent-service:latest .

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f agent

docker-restart:
	docker-compose restart

docker-shell:
	docker-compose exec agent /bin/bash

# =============================================================================
# Cleanup
# =============================================================================

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	rm -rf .ruff_cache 2>/dev/null || true
