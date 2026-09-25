FROM python:3.12-slim
# libpango/libpangoft2/libharfbuzz-subset0: WeasyPrint on Debian >= 11 installed via pip/wheels (Vela's proposal PDFs) —
# https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#debian-11
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client ffmpeg \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY config ./config
COPY supabase ./supabase
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["omnidata", "serve", "api"]
