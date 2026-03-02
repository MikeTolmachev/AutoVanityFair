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
- `src/content/embeddings.py` -- Gemini text-embedding-004 wrapper (32-dim Matryoshka), used by CatBoost reranker
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
- Gemini image models (`gemini-*`): `generate_content()` with `response_modalities=["IMAGE"]`, location `global`
- Imagen models (`imagen-*`): `generate_images()`, location `us-central1`
- Asset generator auto-detects API by model name prefix in `_is_gemini_model()`
- Veo: `veo-3.1-generate-001` via `client.models.generate_videos()` (async, poll for completion)
- Config model name may differ from what's actually available -- always check with `client.models.list()`
- Fast model (`gpt-5-nano`): `ai.generate_fast()` for cheap tasks (asset prompt generation, ranking)
- Generated assets saved to `data/assets/`, served at `/assets/` by FastAPI
- Images converted from PNG to JPEG (quality 95) via Pillow for smaller files + LinkedIn compatibility
- Art style dropdown sends style to prompt generator; Gemini blends it into the image prompt
- Embeddings: `text-embedding-004` at `us-central1` with `output_dimensionality=32`, batch supported

## Auth & Security
- API auth via `OPENLINKEDIN_API_TOKEN` env var (bearer token); disabled when unset (local dev)
- Frontend stores token in `localStorage`, prompts on 401
- All user data in `innerHTML` must use `escapeHtml()`; URLs in `href` must use `safeUrl()`
- API errors: log full exception server-side, return generic message to client
- Limit params bounded with `Query(ge=1, le=500)`

## LinkedIn Automation Gotchas
- Image upload triggers a multi-step Editor overlay (Next → Done) -- must loop through all steps
- Post button may need `force=True` click; add `artdeco-button--primary` selector
- Publishing with images takes 10-20s -- poll for modal close, don't use fixed wait
- Login navigates to `/feed/`; `publish_post` should skip redundant navigation if already there
- Debug screenshots saved to `data/debug/` for post-mortem

## Linting
- `.venv/bin/ruff check api/ src/` -- auto-fix with `--fix`
- E402 suppressed with `noqa` in `api/server.py` (sys.path-dependent imports)

## Testing
- 3 pre-existing test failures (not bugs, stale test expectations):
  - `test_app_config_defaults` -- config defaults differ from local env
  - `test_filter_threshold` -- min_results backfill changed behavior
  - `test_priority_2_feeds` / `test_get_feeds_by_priority` -- feed count mismatch
- Skip with: `--deselect tests/test_config_manager.py::test_app_config_defaults` etc.

## Feed Sources
- Defined in `src/content/rss_aggregator.py` as `PRIORITY_1_FEEDS` through `PRIORITY_4_FEEDS`
- Google AI Blog is P1 (max weight)

## CatBoost Reranker
- Model at `data/reranker_model.cbm`, stats at `.cbm.stats.json`
- Features: 11 numeric + 32 embedding dims + 2 categorical (content_type, source)
- Embeddings stored as JSON in `feed_items.embedding` column
- Train via `POST /api/feed/retrain` -- auto-backfills missing embeddings
- Freshness: 6%/day decay after 2-day grace period, floor at 10%

## Code Style
- Type hints on function signatures
- CRUD classes wrap raw SQL (PostCRUD, CommentCRUD, etc.)
- Streamlit views in `ui/views/`, components in `ui/components/`
- API endpoints in `api/server.py`, frontend is single-file SPA at `web/index.html`
