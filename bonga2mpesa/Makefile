.PHONY: install dev worker beat migrate test lint

install:
	pip install -r requirements.txt

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	celery -A app.workers.celery_app.celery_app worker \
		--loglevel=info \
		--queues=payouts,default,maintenance \
		--concurrency=4

beat:
	celery -A app.workers.celery_app.celery_app beat --loglevel=info

migrate:
	alembic upgrade head

migration:
	alembic revision --autogenerate -m "$(name)"

test:
	pytest -v --tb=short

lint:
	ruff check app tests
	ruff format --check app tests

format:
	ruff format app tests

shell:
	python -c "import asyncio; from app.db.session import AsyncSessionLocal; print('DB session ready')"
