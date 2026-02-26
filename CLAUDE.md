# OpenLinkedIn

## Environment
- Python 3.14 venv at `.venv/` -- always use `.venv/bin/python` and `.venv/bin/pip`
- System pip is PEP 668 locked, do NOT use bare `pip3 install`
- macOS (Darwin), no `timeout` command available

## Architecture
- **Streamlit UI** (legacy): `ui/app.py` -- launched via `python main.py ui`
- **FastAPI + JS UI** (modern): `api/server.py` + `web/index.html` -- launched via `python main.py web`
- **Database**: SQLite at `data/openlinkedin.db`, raw SQL via `src/database/crud.py` (no ORM)
- **Config**: `config/config.yaml` with env var substitution via `src/core/config_manager.py`
- **Secrets**: `.env` file (OPENAI_API_KEY, LINKEDIN_EMAIL, LINKEDIN_PASSWORD, etc.)

## Key Modules
- `src/content/` -- AI content generation (posts, comments), RSS aggregation, reranker
- `src/automation/` -- Playwright-based LinkedIn browser automation
- `src/core/` -- Config, scheduling, safety rate limiting
- `src/database/` -- SQLite models + CRUD classes, ChromaDB vector store

## Commands
- `python main.py setup` -- init dirs and DB
- `python main.py web` -- FastAPI UI (port 8000)
- `python main.py ui` -- Streamlit UI
- `python main.py run` -- scheduler daemon
- `python main.py fetch-feeds` -- CLI feed aggregation
- `.venv/bin/pytest tests/` -- run tests

## Code Style
- Type hints on function signatures
- CRUD classes wrap raw SQL (PostCRUD, CommentCRUD, etc.)
- Streamlit views in `ui/views/`, components in `ui/components/`
- API endpoints in `api/server.py`, frontend is single-file SPA at `web/index.html`
