.PHONY: dev check test lint typecheck migrate
dev:        ## supabase local stack (requires the Supabase CLI + Docker)
	supabase start
lint:
	uv run ruff check src tests
typecheck:
	uv run mypy src
test:
	uv run pytest -q
check: lint typecheck test   ## must pass before any commit (dbt build arrives with M1)
migrate:
	uv run omnidata db migrate
