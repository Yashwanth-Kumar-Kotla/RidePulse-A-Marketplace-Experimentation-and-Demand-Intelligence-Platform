# Builds the FastAPI serving layer only -- data/ridepulse.duckdb is never
# baked into the image (it's gitignored, PRD Section 4: no committed data)
# and is mounted as a volume at runtime instead. Build the warehouse first
# with `make warehouse` before running this container.
FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY api/ api/
COPY ridepulse/ ridepulse/
COPY configs/ configs/

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
