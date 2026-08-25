.PHONY: setup pull-pilot pull-full validate-pilot validate-full warehouse test dashboard api docker-build docker-run

setup:
	uv sync

pull-pilot:
	uv run python -m ridepulse.ingestion.cli pull --pilot

pull-full:
	uv run python -m ridepulse.ingestion.cli pull --full

validate-pilot:
	uv run python -m ridepulse.ingestion.cli validate --pilot

validate-full:
	uv run python -m ridepulse.ingestion.cli validate --full

warehouse:
	uv run python -m ridepulse.warehouse

test:
	uv run pytest -q

dashboard:
	uv run streamlit run dashboard/app.py

api:
	uv run uvicorn api.main:app --reload

docker-build:
	docker build -f docker/Dockerfile -t ridepulse-api .

docker-run:
	docker run --rm -p 8000:8000 -v $$(pwd)/data:/app/data ridepulse-api
