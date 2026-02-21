# OpenLinkedIn

LinkedIn automation system with AI-powered content generation, RSS/API aggregation, human-in-the-loop approval, and browser-based publishing.

## Features

- **AI Content Generation** -- Generate LinkedIn posts and comments using OpenAI or Anthropic (Claude), grounded in your knowledge base via RAG
- **RSS/API Feed Aggregation** -- Aggregate content from 20+ production-focused AI sources with multi-stage relevance scoring for executive positioning
- **Human-in-the-Loop** -- All generated content goes through a Streamlit review UI before publishing
- **Browser Automation** -- Publish to LinkedIn via Playwright with stealth mode, adapted from OpenOutreach
- **Scheduling** -- APScheduler with CET timezone: posts during morning hours, comments every 2 hours
- **Safety System** -- Hourly/daily/weekly rate limits, error rate monitoring, automatic cooldown

## Quick Start

### 1. Clone and set up the environment

```bash
cd OpenLinkedIn
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your API keys and LinkedIn credentials
```

Required variables:
| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key (if using OpenAI provider) |
| `ANTHROPIC_API_KEY` | Anthropic API key (if using Claude provider) |
| `LINKEDIN_EMAIL` | LinkedIn account email |
| `LINKEDIN_PASSWORD` | LinkedIn account password |

### 3. Run initial setup

```bash
python main.py setup
```

This creates data directories, initializes the SQLite database, and validates your config.

### 4. (Optional) Install Playwright browsers

```bash
python -m playwright install chromium
```

### 5. Launch the UI

```bash
streamlit run ui/app.py
```

Opens at `http://localhost:8501` with tabs for:
- **Posts Queue** -- Review, edit, approve, or reject generated posts
- **Comments Queue** -- Review comments with confidence scores
- **Feed Aggregator** -- Browse scored RSS/API content, save to knowledge base
- **Analytics** -- Charts for posts/comments per week, approval rates, action log
- **Content Library** -- Manage RAG knowledge base documents
- **Settings** -- View configuration (edit via `config/config.yaml`)

## CLI Commands

```
python main.py setup                          # Initialize directories and database
python main.py ui                             # Launch Streamlit UI
python main.py run                            # Start the scheduler daemon
python main.py generate-post [topic]          # Generate a single post
python main.py generate-post --strategy pov "AI regulation"
python main.py fetch-feeds                    # Fetch and score RSS/API feeds
python main.py fetch-feeds --priorities 1,2   # Fetch only priority 1 and 2 feeds
python main.py fetch-feeds --min-score 20     # Only show items scoring 20+
```

## Configuration

Edit `config/config.yaml` to customize:

```yaml
ai:
  provider: "openai"         # or "anthropic"
  openai:
    model: "gpt-4o"
    temperature: 0.7
  anthropic:
    model: "claude-sonnet-4-20250514"

scheduling:
  timezone: "Europe/Berlin"
  posts:
    cron_hour: "7-9"         # Post generation window (CET)
    max_per_day: 2
  comments:
    interval_hours: 2        # Comment generation interval
    active_start_hour: 9     # Active hours start (CET)
    active_end_hour: 21      # Active hours end (CET)

safety:
  hourly_action_limit: 8
  daily_action_limit: 30
  weekly_action_limit: 150
  error_rate_threshold: 0.3
  cooldown_minutes: 30

aggregation:
  enabled: true
  default_priorities: [1, 2]
  min_relevance_score: 10.0
  auto_save_threshold: 35.0  # Auto-save high-scoring feed items to library
```

## Feed Aggregator

The system aggregates content from 20+ RSS feeds and APIs across 4 priority tiers:

| Priority | Category | Sources |
|----------|----------|---------|
| **P1** | Production AI & MLOps | Hugging Face Papers, MLOps Community, The New Stack, Neptune.ai, W&B, PyTorch, TensorFlow, NVIDIA |
| **P2** | Engineering Research | Papers with Code, Google AI, Meta AI, OpenAI |
| **P3** | Infrastructure & Deployment | Ray, AWS ML, Google Cloud AI, Azure AI |
| **P4** | Community & Discussion | Reddit r/ML, Hacker News, LangChain, LlamaIndex |

### Content Scoring

Each item is scored through three stages:

1. **Production Relevance** (40% weight) -- Keywords like "deployment", "MLOps", "inference optimization", "at scale" with weighted scoring. Production + implementation combinations get bonus points.
2. **Executive Positioning** (25% weight) -- Scale indicators, leadership signals, operational excellence markers, team/organizational keywords.
3. **Keyword Match** (35% weight) -- Matches against a taxonomy of 200+ keywords across 8 categories (Core ML, Frameworks, LLM/GenAI, Production, Infrastructure, Data/Vector, Emerging Tech, Business).

Content type multipliers are then applied:

| Content Type | Multiplier |
|--------------|------------|
| Production case study | 2.0x |
| Infrastructure deep-dive | 2.0x |
| Framework comparison | 1.5x |
| Benchmark with real workloads | 1.5x |
| Research with code | 1.2x |
| Technical tutorial | 1.2x |
| General | 1.0x |
| Pure research | 0.8x |

## Project Structure

```
OpenLinkedIn/
├── config/
│   └── config.yaml              # All configuration
├── src/
│   ├── core/
│   │   ├── config_manager.py    # YAML + env var config with Pydantic
│   │   ├── rate_limiter.py      # Sliding-window rate limiter
│   │   ├── safety_monitor.py    # Multi-tier safety system
│   │   └── scheduler.py        # APScheduler with CET timezone
│   ├── content/
│   │   ├── generator.py         # AI provider abstraction (OpenAI/Anthropic)
│   │   ├── prompts.py           # Prompt templates for posts and comments
│   │   ├── validators.py        # Content validation (length, placeholders)
│   │   ├── rag_engine.py        # RAG context retrieval
│   │   ├── post_generator.py    # Post generation orchestrator
│   │   ├── comment_generator.py # Comment generation with confidence scoring
│   │   ├── rss_aggregator.py    # RSS/API feed aggregation
│   │   ├── content_filter.py    # Multi-stage content scoring
│   │   └── keyword_taxonomy.py  # 200+ keyword taxonomy with priorities
│   ├── automation/
│   │   ├── openoutreach_adapter.py  # OpenOutreach wrapper with fallbacks
│   │   ├── session_manager.py       # Playwright browser session
│   │   ├── feed_scraper.py          # LinkedIn feed DOM scraping
│   │   └── linkedin_bot.py         # High-level LinkedIn actions
│   ├── database/
│   │   ├── models.py            # SQLite schema (posts, comments, feed_items, etc.)
│   │   ├── crud.py              # All CRUD operations
│   │   └── vector_store.py      # ChromaDB wrapper for RAG embeddings
│   └── utils/
│       ├── logging_config.py    # Rotating file + console logging
│       └── helpers.py           # Timestamps, text utils, URL validation
├── ui/
│   ├── app.py                   # Streamlit main entry
│   ├── pages/
│   │   ├── posts_queue.py       # Post review/approval
│   │   ├── comments_queue.py    # Comment review/approval
│   │   ├── feed_aggregator.py   # RSS feed browsing and scoring
│   │   ├── analytics.py         # Charts and activity log
│   │   ├── content_library.py   # RAG knowledge base management
│   │   └── settings.py          # Config viewer
│   └── components/
│       ├── queue_card.py        # Reusable approval card
│       ├── stats_widget.py      # Sidebar metrics
│       └── editor.py            # Inline content editor
├── scripts/
│   ├── initial_setup.py         # Full setup with Playwright + OpenOutreach
│   ├── seed_posts.py            # Seed RAG knowledge base
│   ├── test_openai.py           # Test API connectivity
│   └── test_linkedin_login.py   # Test browser login
├── tests/
│   ├── conftest.py              # Fixtures and mock providers
│   ├── test_config_manager.py
│   ├── test_crud.py
│   ├── test_safety_monitor.py
│   ├── test_generators.py
│   ├── test_content_filter.py
│   └── test_rss_aggregator.py
├── main.py                      # CLI entry point
├── pyproject.toml
├── .env.example
└── .gitignore
```

## Running Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

All tests run with mocked externals (no API keys or browser needed).

## Typical Workflow

1. **Aggregate content**: Fetch RSS feeds via the Feed Aggregator tab or `python main.py fetch-feeds`
2. **Build knowledge base**: Save high-scoring articles to the Content Library for RAG grounding
3. **Generate posts**: Click "Generate New Post" in the sidebar or use `python main.py generate-post "topic"`
4. **Review and approve**: Review generated content in the Posts/Comments Queue tabs
5. **Publish**: Approved content is published to LinkedIn via browser automation (requires `python main.py run`)

## OpenOutreach Integration

The browser automation layer can optionally use [OpenOutreach](https://github.com/eracle/OpenOutreach). To set up:

```bash
python scripts/initial_setup.py
```

This clones OpenOutreach into `external/OpenOutreach/` and imports its Django-free Playwright functions (`build_playwright`, `human_type`, `playwright_login`). If OpenOutreach is not available, standalone fallback implementations are used.

## License

MIT
