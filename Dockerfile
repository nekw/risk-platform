FROM python:3.11-slim

# Install uv for fast dependency resolution and installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /workspace

COPY requirements.txt .
RUN uv pip install --no-cache --system -r requirements.txt

COPY . .

EXPOSE 8000
