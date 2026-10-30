<p align="center">
  <img src="docs/images/hero.png" alt="Competitor price monitoring and lead-to-CRM automation" width="100%">
</p>

<p align="center">
  <a href="https://github.com/Yusufislamyetkin/python-automation-scraping-toolkit/actions/workflows/ci.yml"><img src="https://github.com/Yusufislamyetkin/python-automation-scraping-toolkit/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Playwright-2EAD33?logo=playwright&logoColor=white" alt="Playwright">
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/n8n-workflows-EA4B71?logo=n8n&logoColor=white" alt="n8n">
  <img src="https://img.shields.io/badge/Make-blueprints-6D00CC?logo=make&logoColor=white" alt="Make">
  <img src="https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT">
</p>

<h3 align="center">Know every competitor price change by 7 AM, keep it all in a Google Sheet,<br>and turn website form fills into scored HubSpot contacts, without copy-paste.</h3>

---

## The problem it solves

A small e-commerce shop sells the same products as several competitors. Every morning someone opens their sites to check prices, notes who ran out of stock, updates a spreadsheet, and forwards contact-form emails to sales. That work is slow and easy to forget, and the important change gets noticed a week late.

**This toolkit does it automatically:**

| | |
|---|---|
| 🕷️ **Scrapes** competitor catalogues every day: static HTML and JavaScript-rendered pages | 🔎 **Detects** price drops, price rises, out-of-stock and back-in-stock |
| 📊 **Updates a Google Sheet**: live `products` tab, `changes` log, `leads` log | 🔔 **Alerts** on Slack or Telegram, with email as a fallback |
| 🎯 **Scores website leads**: validated, deduplicated, enriched with domain and country | 🤝 **Upserts qualified leads into HubSpot** and notifies the sales team |
| 🧩 **Plugs into n8n and Make**: ready-to-import workflows included | 📈 **Logs every run**: status, duration, item counts, errors, raw HTML of failures |

## See it work

### Daily run: scrape → detect → Sheet → alert

<p align="center"><img src="docs/images/demo-terminal.gif" alt="Terminal: a scrape run finding 6 price and stock changes" width="100%"></p>

### The Google Sheet fills itself

<p align="center"><img src="docs/images/sheet-filling.gif" alt="Spreadsheet changes tab filling with detected price and stock changes" width="100%"></p>

### One alert per run, not one per product

<p align="center"><img src="docs/images/slack-alert.png" alt="Price alert message with drops, rises and back-in-stock items" width="100%"></p>

### Website lead → score → HubSpot

<p align="center"><img src="docs/images/lead-scoring.png" alt="Lead payload and the scored, enriched response" width="100%"></p>

### Ready-made n8n and Make workflows

<p align="center"><img src="docs/images/workflows.png" alt="Workflow (a) daily price monitor and workflow (b) lead to HubSpot" width="100%"></p>

## What this automates

| Before | After |
|---|---|
| Someone checks competitor sites by hand | A scheduled job scrapes the catalogue daily and stores the full price history |
| Price moves are noticed late, or never | Drops, rises and stock changes are detected the same morning |
| The tracking spreadsheet is updated by copy-paste | The Google Sheet updates itself |
| Alerts depend on someone remembering to look | One Slack or Telegram summary per run; email if chat is down |
| Form leads sit in an inbox | Leads are validated, deduplicated, enriched, scored, and the good ones land in HubSpot |
| "Did last night's job run?" | Each run has a log entry: status, duration, counts, errors |

**Estimated time saved.** These figures are *estimates*, assuming about 200 tracked products across 3 competitor sites and about 30 leads per week:

| Task | Manual (estimate) | Automated (estimate) |
|---|---|---|
| Daily price and stock check | ~2.5 h/week | ~5 min/week reading alerts |
| Updating the tracking sheet | ~1 h/week | 0 |
| Copying and triaging leads into the CRM | ~1 h/week | 0 |
| **Total** | **~4.5 h/week** | **~5–10 min/week** |

## Architecture

<p align="center"><img src="docs/images/architecture.png" alt="Architecture: sources, toolkit services, destinations" width="100%"></p>

```mermaid
flowchart LR
    subgraph Sources
        B[Competitor store<br/>static HTML]
        Q[JS-rendered store]
        F[Website form]
    end
    subgraph Toolkit["Toolkit (Docker Compose)"]
        direction TB
        API[FastAPI<br/>REST + webhooks]
        W[ARQ worker<br/>daily cron]
        R[(Redis)]
        S[Scraper interface<br/>httpx + selectolax / Playwright]
        CD[Change detection]
        LS[Lead pipeline<br/>validate · dedupe · enrich · score]
        DB[(PostgreSQL)]
        N8N[n8n]
    end
    subgraph Destinations
        GS[Google Sheets]
        SL[Slack / Telegram]
        EM[Email]
        HS[HubSpot CRM]
    end
    B --> S
    Q --> S
    W --> S
    API -- enqueue --> R --> W
    S --> CD --> DB
    F -- POST /leads --> API --> LS --> DB
    CD --> GS & SL
    SL -. fallback .-> EM
    LS -- qualified --> HS
    LS --> GS
    N8N -- HTTP + API key --> API
    N8N --> GS & SL & HS & EM
```

Run the integrations **inside the Python service** (credentials in `.env`) or **orchestrate them from n8n or Make** (credentials in the automation tool, with the toolkit acting as the API). The same codebase supports both.

## Quick start (3 commands)

```bash
git clone https://github.com/Yusufislamyetkin/python-automation-scraping-toolkit.git && cd python-automation-scraping-toolkit
cp .env.example .env
docker compose up -d --build
```

| Open | URL |
|---|---|
| API docs (Swagger) | http://localhost:8000/docs |
| Health and integration status | http://localhost:8000/health |
| n8n editor | http://localhost:5678 |

```bash
# run a scrape and get the change events back
curl -X POST "http://localhost:8000/jobs/scrape?target=books&wait=true" -H "X-API-Key: change-me"

# browse the catalogue, download a CSV
curl "http://localhost:8000/products?limit=5"
curl -o products.csv http://localhost:8000/export/products.csv
```

No accounts are needed to try it. Without Google or HubSpot credentials, the toolkit runs in **demo mode**: it writes the same rows to `data/demo/*.csv` and logs what it *would* send. Add credentials to `.env` and `/health` switches those integrations to `live`.

## API

<p align="center"><img src="docs/images/swagger.png" alt="Swagger UI of the toolkit API" width="85%"></p>

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/jobs/scrape?target=books\|quotes[&wait=true]` | `X-API-Key` | Queue a scrape (202). With `wait=true` it runs inline and returns the job plus its change events, which suits n8n and Make |
| `GET` | `/jobs/{id}` | - | Run log: status, duration, counts, error, failure samples with snapshot paths |
| `GET` | `/products?source=&in_stock=&limit=&offset=` | - | Current catalogue |
| `GET` | `/products/{id}/history` | - | Price and stock history |
| `GET` | `/changes?since=2026-10-30T00:00:00Z` | - | Change events since a timestamp |
| `POST` | `/leads` | `X-API-Key` | Lead intake. Returns 201 for a new lead, or 200 with `duplicate: true` for a repeat |
| `GET` | `/export/products.csv` | - | CSV export |
| `GET` | `/health` | - | Database status and per-integration `live` / `demo` / `off` |

```bash
curl -X POST http://localhost:8000/leads -H "X-API-Key: change-me" -H "Content-Type: application/json" \
  -d '{"email":"jane@acmeoutdoor.de","name":"Jane Doe","company":"Acme Outdoor GmbH","budget_usd":6000,"message":"We need a pricing quote for monitoring 500 competitor products."}'
```

```json
{"id": 1, "email": "jane@acmeoutdoor.de", "score": 95, "status": "synced", "qualified": true,
 "duplicate": false, "company_domain": "acmeoutdoor.de", "country": "DE",
 "score_reasons": ["+30 business email", "+10 company given", "+25 budget >= 5k",
                   "+10 detailed message", "+15 buying intent", "+5 target market"]}
```

The lead score comes from readable rules in [`services/leads.py`](src/toolkit/services/leads.py), so a sales team can tune them without touching a model.

## CLI

```bash
toolkit scrape books --pages 2       # run now: store history, detect changes, update Sheet, alert
toolkit scrape quotes                # JavaScript-rendered target via headless Chromium
toolkit export --format xlsx         # data/exports/products.xlsx (or --format csv)
toolkit sync-sheets                  # rewrite the "products" tab from the database
toolkit simulate-drift --count 5     # demo helper: alter stored prices so the next run raises alerts
```

Inside Docker, prefix these with `docker compose exec api`.

## n8n and Make workflows

| Workflow | n8n | Make |
|---|---|---|
| (a) Daily trigger → `/jobs/scrape` → change events → Sheets + Slack | [`daily-price-monitor.json`](workflows/n8n/daily-price-monitor.json) | [`daily-price-monitor.blueprint.json`](workflows/make/daily-price-monitor.blueprint.json) |
| (b) Form webhook → `/leads` → score ≥ threshold → HubSpot + Gmail | [`lead-intake.json`](workflows/n8n/lead-intake.json) | [`lead-intake.blueprint.json`](workflows/make/lead-intake.blueprint.json) |

### Import into n8n (included in the compose stack)

1. Open http://localhost:5678 and create the local owner account.
2. Go to **Workflows → Add workflow → ⋯ → Import from File** and pick a file from `workflows/n8n/`. To import both at once from the CLI, run
   `docker compose exec n8n n8n import:workflow --separate --input=/workflows`.
3. Attach credentials on the nodes marked with a warning:
   - **Google Sheets**: service account or OAuth2. The sheet needs a `changes` tab with the header `detected_at,type,source,title,old,new,pct_change,url`.
   - **HubSpot**: *App Token*, using a private-app token with the `crm.objects.contacts.write` scope.
   - **Gmail**: OAuth2.
4. Compose passes `.env` values to n8n: `TOOLKIT_API_URL`, `TOOLKIT_API_KEY` (= `API_KEY`), `GOOGLE_SHEET_ID`, `SLACK_WEBHOOK_URL`, `SALES_EMAIL`, `LEAD_SCORE_THRESHOLD`. Run `docker compose up -d n8n` after you edit `.env`.
5. Click **Test workflow**, then switch it to **Active**. Point your website form at `http://<host>:5678/webhook/lead-intake`.

### Import into Make

1. Go to **Scenarios → Create a new scenario → ⋯ → Import Blueprint** and choose a file from `workflows/make/`.
2. Replace the placeholders: `https://YOUR-TOOLKIT-HOST`, `YOUR_API_KEY`, `YOUR_SHEET_ID`, the Slack webhook URL and `sales@your-company.com`.
3. Attach your Google Sheets, HubSpot and Gmail connections. Make never exports connections, so this is always a manual step.
4. For (a), schedule the scenario *Every day* at 07:00. For (b), copy the webhook URL into your form.
5. Make runs in the cloud, so the toolkit must be reachable from the internet: deploy it, or for a quick test use `cloudflared tunnel --url http://localhost:8000`.

## Reliability

| Concern | How it is handled |
|---|---|
| **Retries** | `tenacity` retries network errors, 429 and 5xx with randomized exponential backoff (4 attempts), for both scraping and HubSpot. Other 4xx responses fail fast. |
| **Polite scraping** | robots.txt is checked and cached per host. Each request carries a clear `User-Agent`. A minimum delay between requests, a concurrency cap and a page cap are configurable, and an optional proxy works for both httpx and Playwright. |
| **A bad row never stops the job** | Each product card is parsed on its own, and each item is stored in its own database SAVEPOINT. A broken card or a DB error affects only that row; the run ends `partial`. |
| **Snapshot on failure** | When a page or card does not parse, its raw HTML is saved under `data/snapshots/` and the path is attached to the run log. |
| **Idempotency** | Leads are unique on `(email, sha256(normalized payload))`, so a resubmitted form returns the existing lead. The constraint also catches two identical requests arriving at the same moment. HubSpot uses *upsert by email*, so contacts are never duplicated. Products are unique on `(source, external_id)`. |
| **Run logs** | Each run is stored in `job_runs` with status, start and finish time, duration, totals, error text and failure samples (`GET /jobs/{id}`). Logs are structured JSON (`structlog`) and tagged with the `job_id`. |
| **Alerts never break a run** | Notification failures are logged and the scrape result stays saved. Email is used only if every chat channel fails. A first run records new products quietly instead of sending one alert per product. |

## Configuration

Every setting is an environment variable; see [`.env.example`](.env.example). No secrets live in the repository.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://toolkit:toolkit@localhost:5434/toolkit` | PostgreSQL |
| `REDIS_URL` | `redis://localhost:6379/0` | Job queue (without Redis, the API runs jobs in-process) |
| `API_KEY` | `change-me` | `X-API-Key` header required on `POST` endpoints |
| `USER_AGENT` | `PriceMonitorBot/0.1 (+repo URL)` | Bot identity sent to target sites |
| `REQUEST_DELAY_SECONDS` / `MAX_CONCURRENCY` / `MAX_PAGES` | `1.0` / `4` / `5` | Politeness and scope |
| `BOOKS_FETCH_DETAILS` | `false` | Also fetch product pages for the exact stock count, category and UPC |
| `PROXY_URL` | - | HTTP(S) proxy for scraping |
| `RESPECT_ROBOTS_TXT` | `true` | Honour robots.txt |
| `SCHEDULE_HOUR_UTC` / `SCHEDULE_TARGETS` | `6` / `["books"]` | Daily schedule in the worker |
| `PRICE_CHANGE_THRESHOLD_PCT` | `0` | Ignore price moves smaller than this |
| `LEAD_SCORE_THRESHOLD` | `60` | Score at which a lead is qualified |
| `GOOGLE_SERVICE_ACCOUNT_FILE` / `GOOGLE_SHEET_ID` | - | Google Sheets (share the sheet with the service-account email) |
| `HUBSPOT_TOKEN` | - | HubSpot private-app token |
| `SLACK_WEBHOOK_URL` | - | Slack incoming webhook |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | - | Telegram alerts |
| `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASSWORD` `SMTP_FROM` `ALERT_EMAIL_TO` | - | Email fallback |

## Data model

```mermaid
erDiagram
    products ||--o{ price_snapshots : has
    products ||--o{ change_events : has
    job_runs ||--o{ price_snapshots : produced
    job_runs ||--o{ change_events : produced
    products {
        int id PK
        string source
        string external_id
        string title
        numeric current_price
        bool in_stock
        jsonb extra
    }
    price_snapshots {
        int id PK
        int product_id FK
        uuid job_run_id FK
        numeric price
        bool in_stock
        timestamptz scraped_at
    }
    change_events {
        int id PK
        int product_id FK
        string type
        string old_value
        string new_value
        numeric pct_change
        timestamptz notified_at
    }
    job_runs {
        uuid id PK
        string status
        int duration_ms
        int items_ok
        int items_failed
        text error
        jsonb meta
    }
    leads {
        int id PK
        string email
        string payload_hash
        int score
        string status
        string hubspot_contact_id
    }
```

## Tech stack

| Layer | Tools |
|---|---|
| Scraping | `httpx` (async) + `selectolax` for static pages, Playwright (Chromium) for JavaScript pages, `tenacity` |
| API | FastAPI, Pydantic v2, header API-key auth |
| Storage | PostgreSQL 16, SQLAlchemy 2.0 async, Alembic |
| Jobs | ARQ + Redis, daily cron, run log table |
| Integrations | gspread (Google Sheets), HubSpot CRM v3, Slack and Telegram webhooks, SMTP |
| Automation | n8n (self-hosted in compose), Make blueprints |
| Tooling | uv, Ruff, mypy (strict), pytest + pytest-asyncio, respx, Testcontainers, structlog, Typer |
| Delivery | Docker Compose, GitHub Actions (lint, type-check, tests, Docker build) |

## Project layout

```
src/toolkit/
  scraping/      Scraper interface, polite HTTP client, static and JS-rendered scrapers
  services/      change detection, job runs, lead pipeline, export, job dispatch
  integrations/  Sheets, HubSpot, Slack/Telegram/SMTP clients, fakes, demo mode, business flows
  api/           FastAPI app and routers
  worker/        ARQ worker and daily cron
  db/            models, session, queries
migrations/      Alembic
workflows/       n8n exports and Make blueprints
tests/           parser tests on saved HTML, mocked APIs, fakes, Testcontainers PostgreSQL
docs/images/     screenshots and GIFs
```

## Testing

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
```

The test suite covers:

- parser tests on saved HTML pages, including a broken card and a layout change;
- respx-mocked HubSpot, Slack and Telegram calls;
- fake Sheets and HubSpot clients;
- API tests;
- a Testcontainers PostgreSQL integration test that runs the real Alembic migrations.

CI runs all of it on every push.

## Notes

- The included targets are the public scraping sandboxes books.toscrape.com and quotes.toscrape.com/js. A new site is one new parser behind the same `Scraper` interface.
- The sandbox sites keep their prices fixed, so use `toolkit simulate-drift` to see alerts in a demo.

## Roadmap

- [ ] Airtable as an alternative to Google Sheets
- [ ] Pipedrive as an alternative CRM
- [ ] Zapier versions of both workflows
- [ ] Residential or rotating proxy pool with per-domain rules
- [ ] LLM-assisted extraction for sites without stable HTML
- [ ] Cross-competitor price comparison (match the same product across sites)

## License

MIT · built by [Yusuf İslam Yetkin](https://github.com/Yusufislamyetkin)
