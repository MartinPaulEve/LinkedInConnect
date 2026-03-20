FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files first for caching
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv sync --no-dev --no-install-project

# Copy source code
COPY . .

# Install the project itself
RUN uv sync --no-dev

ENTRYPOINT ["uv", "run", "linkedin-sync"]
