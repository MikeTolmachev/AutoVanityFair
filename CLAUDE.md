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

## Vertex AI / Asset Generation
- Uses `google.genai` SDK (NOT old `vertexai.preview.vision_models`)
- Imagen: `imagen-4.0-generate-001` via `client.models.generate_images()` -- verified working
- Veo: `veo-3.1-generate-001` via `client.models.generate_videos()` (async, poll for completion)
- Config model name may differ from what's actually available -- always check with `client.models.list()`
- Fast model (`gpt-5-nano`): `ai.generate_fast()` for cheap tasks (asset prompt generation, ranking)
- Generated assets saved to `data/assets/`, served at `/assets/` by FastAPI

## Auth & Security
- API auth via `OPENLINKEDIN_API_TOKEN` env var (bearer token); disabled when unset (local dev)
- Frontend stores token in `localStorage`, prompts on 401
- All user data in `innerHTML` must use `escapeHtml()`; URLs in `href` must use `safeUrl()`
- API errors: log full exception server-side, return generic message to client
- Limit params bounded with `Query(ge=1, le=500)`

## Code Style
- Type hints on function signatures
- CRUD classes wrap raw SQL (PostCRUD, CommentCRUD, etc.)
- Streamlit views in `ui/views/`, components in `ui/components/`
- API endpoints in `api/server.py`, frontend is single-file SPA at `web/index.html`
