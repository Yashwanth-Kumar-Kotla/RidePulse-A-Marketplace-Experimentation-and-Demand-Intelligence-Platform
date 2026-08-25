# Builds the FastAPI serving layer only -- data/ridepulse.duckdb is never
# baked into the image (it's gitignored, PRD Section 4: no committed data)
# and is mounted as a volume at runtime instead. Build the warehouse first
# with `make warehouse` before running this container.
FROM python:3.12-slim

# libgomp1 (OpenMP runtime) is required by LightGBM's native library and is
# NOT included in python:3.12-slim by default -- found by actually running
# the built container, not assumed: it failed at import time with
# "OSError: libgomp.so.1: cannot open shared object file: No such file or
# directory", a known gotcha with minimal Debian base images.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY api/ api/
COPY ridepulse/ ridepulse/
COPY configs/ configs/

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
