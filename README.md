# Python Automation & Scraping Toolkit

[![CI](https://github.com/Yusufislamyetkin/python-automation-scraping-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/Yusufislamyetkin/python-automation-scraping-toolkit/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-2EAD33?logo=playwright&logoColor=white)
![n8n](https://img.shields.io/badge/n8n-workflows-EA4B71?logo=n8n&logoColor=white)
![Make](https://img.shields.io/badge/Make-blueprints-6D00CC?logo=make&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

**Watch competitor prices and stock every day, get alerts the moment something changes, keep it all in a Google Sheet, and push website leads straight into HubSpot. One `docker compose up`, no accounts required to try it.**

> The business story: a small e-commerce shop sells the same products as several competitors. Every morning the shop needs to know who dropped a price, who ran out of stock, and who is back in stock. It also gets leads from a contact form that should land in the CRM, scored, without anyone copy-pasting.

| Google Sheet filling up | Slack alert | n8n canvas | HubSpot contact |
|---|---|---|---|
| _GIF placeholder:_ `docs/images/sheet.gif` | _Screenshot placeholder:_ `docs/images/slack-alert.png` | _Screenshot placeholder:_ `docs/images/n8n-canvas.png` | _Screenshot placeholder:_ `docs/images/hubspot-contact.png` |

---

## What this automates

| Today (manual) | With the toolkit |
|---|---|
| Someone opens competitor sites and checks prices by hand | A scheduled job scrapes the catalogue every day and stores the full price history |
| Price changes are noticed late, or never | Price drops, price rises, out-of-stock and back-in-stock are detected automatically |
| A spreadsheet is updated by copy-paste | The Google Sheet is refreshed: a `products` tab with current prices, a `changes` log tab |
| Alerts depend on someone remembering to look | One Slack or Telegram message per run summarises what changed; email is the fallback |
| Form leads sit in an inbox | Each lead is validated, deduplicated, enriched (company domain, country), scored, and qualified leads are upserted into HubSpot |
| "Did that job run last night?" | Every run is logged with status, duration, item counts and the error, queryable over the API |

**Estimated time saved.** These numbers are *estimates*, not measurements. They assume about 200 tracked products across 3 competitor sites and about 30 form leads per week:

| Task | Manual effort (estimate) | After automation (estimate) |
|---|---|---|
| Daily price and stock check | ~30 min/day, so ~2.5 h/week | ~5 min/week to read alerts |
| Updating the tracking sheet | ~1 h/week | 0 |
| Copying leads into the CRM and triaging them | ~2 min/lead, so ~1 h/week | 0 (only qualified leads need a human) |
| **Total** | **~4.5 h/week** | **~5–10 min/week** |

Your numbers depend on catalogue size, how many sites you track, and lead volume.

## Architecture

```mermaid
flowchart LR
    subgraph Sources
        B[books.toscrape.com<br/>static HTML]
        Q[quotes.toscrape.com/js<br/>JavaScript-rendered]
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
        DB[(PostgreSQL<br/>products · price_snapshots<br/>change_events · leads · job_runs)]
        N8N[n8n]
    end

    subgraph Destinations
        GS[Google Sheets]
        SL[Slack / Telegram]
        EM[Email SMTP / Gmail]
        HS[HubSpot CRM]
    end

    B --> S
    Q --> S
    W -- scrape_task --> S
    API -- enqueue --> R --> W
    S --> CD --> DB
    F -- POST /leads --> API --> LS --> DB
    CD --> GS & SL
    SL -. all channels failed .-> EM
    LS -- qualified --> HS
    LS --> GS
    N8N -- HTTP + X-API-Key --> API
    N8N --> GS & SL & HS & EM
```

Flow 1, price monitoring: **scrape → store history → detect changes → update the Sheet → alert**.
Flow 2, leads: **form webhook → validate and dedupe → enrich → score → upsert to HubSpot → append to the Sheet → notify**.

Both flows can run **inside the Python service** (set the credentials in `.env`) or be **orchestrated by n8n / Make** (credentials live in the automation tool and the toolkit is just an API). Pick one place per integration so a lead is not pushed twice.

## Quick start (3 commands)

```bash
git clone https://github.com/Yusufislamyetkin/python-automation-scraping-toolkit.git && cd python-automation-scraping-toolkit
cp .env.example .env
docker compose up -d --build
```

Then:

- API docs: http://localhost:8000/docs
- Health and integration modes: http://localhost:8000/health
- n8n: http://localhost:5678

Run a scrape and look at the result:

```bash
curl -X POST "http://localhost:8000/jobs/scrape?target=books&wait=true" -H "X-API-Key: change-me"
curl "http://localhost:8000/products?limit=5"
curl -o products.csv http://localhost:8000/export/products.csv
```

With no Google or HubSpot credentials the toolkit runs in **demo mode**. Instead of calling those services, it writes `data/demo/sheet_*.csv` and `data/demo/hubspot_contacts.csv` and logs `would_send_*` lines.

> **Seeing a price-drop alert in a demo.** The sandbox sites never change their prices. To make the next scrape produce change events, nudge a few stored prices first:
> `docker compose exec api toolkit simulate-drift --count 5`, then `docker compose exec api toolkit scrape books`.

### Local development (without Docker for the app)

```bash
uv sync
uv run playwright install chromium
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn toolkit.api.main:app --reload
```

## API

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/jobs/scrape?target=books\|quotes[&wait=true]` | `X-API-Key` | Queue a scrape (202). With `wait=true` it runs inline and returns the job plus its change events, which is convenient for n8n and Make |
| `GET` | `/jobs/{id}` | - | Run log: status, duration, item counts, error, failures with snapshot paths |
| `GET` | `/products?source=&in_stock=&limit=&offset=` | - | Current catalogue |
| `GET` | `/products/{id}/history` | - | Price and stock history |
| `GET` | `/changes?since=2026-10-30T00:00:00Z[&include_new=true]` | - | Change events |
| `POST` | `/leads` | `X-API-Key` | Lead intake. Returns 201 for a new lead, or 200 with `duplicate: true` for a repeat |
| `GET` | `/export/products.csv` | - | CSV export |
| `GET` | `/health` | - | DB status and which integrations are `live` / `demo` / `off` |

Example lead:

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

Scoring is a transparent rule set in [`services/leads.py`](src/toolkit/services/leads.py), not a model, so sales can read and tune it. Country enrichment comes from the form field or the domain's country TLD; it is a heuristic, not a lookup service.

## CLI

```bash
toolkit scrape books --pages 2       # run now, store history, detect changes, alert
toolkit scrape quotes                # JS-rendered target via Playwright
toolkit export --format xlsx         # data/exports/products.xlsx (or --format csv)
toolkit sync-sheets                  # rewrite the "products" tab from the database
toolkit simulate-drift --count 5     # DEMO ONLY: alter stored prices to trigger alerts
```

Inside Docker, prefix the commands with `docker compose exec api`.

## n8n and Make workflows

| Workflow | n8n | Make |
|---|---|---|
| (a) Daily trigger → `/jobs/scrape` → change events → Sheets + Slack | [`workflows/n8n/daily-price-monitor.json`](workflows/n8n/daily-price-monitor.json) | [`workflows/make/daily-price-monitor.blueprint.json`](workflows/make/daily-price-monitor.blueprint.json) |
| (b) Form webhook → `/leads` → score ≥ threshold → HubSpot + Gmail | [`workflows/n8n/lead-intake.json`](workflows/n8n/lead-intake.json) | [`workflows/make/lead-intake.blueprint.json`](workflows/make/lead-intake.blueprint.json) |

### Import into n8n (self-hosted in this compose)

1. Run `docker compose up -d` and open http://localhost:5678. Create the local owner account on first start.
2. Go to **Workflows → Add workflow → ⋯ menu → Import from File** and pick a file from `workflows/n8n/`.
   Alternatively, import both from the CLI:
   `docker compose exec n8n n8n import:workflow --separate --input=/workflows`
3. Open each node with a warning triangle and pick or create its credential:
   - **Google Sheets**: a Google service account or OAuth2. The sheet needs a `changes` tab with the header `detected_at,type,source,title,old,new,pct_change,url`.
   - **HubSpot**: *App Token* auth with a private-app token that has the `crm.objects.contacts.write` scope.
   - **Gmail**: OAuth2.
4. Values the workflows read from the environment are passed to the n8n container by compose from your `.env`: `TOOLKIT_API_URL` (already `http://api:8000`), `TOOLKIT_API_KEY` (= `API_KEY`), `GOOGLE_SHEET_ID`, `SLACK_WEBHOOK_URL`, `SALES_EMAIL`, `LEAD_SCORE_THRESHOLD`. After changing `.env`, run `docker compose up -d n8n`.
5. Click **Test workflow** once, then toggle **Active**. The lead webhook URL is `http://localhost:5678/webhook/lead-intake`; point your form there.

Both n8n files were import-tested with `n8n import:workflow` on n8n 1.74.1. The lead workflow's webhook → `/leads` → reply path was run in this compose stack with an unqualified lead. The HubSpot, Gmail, Google Sheets and Slack nodes need your own credentials and have not been run.

### Import into Make

1. In Make go to **Scenarios → Create a new scenario → ⋯ → Import Blueprint** and choose a file from `workflows/make/`.
2. Replace the placeholders `https://YOUR-TOOLKIT-HOST`, `YOUR_API_KEY`, `YOUR_SHEET_ID`, the Slack webhook URL and `sales@your-company.com`.
3. Click each Google Sheets, HubSpot and Gmail module and attach your connection. Make never exports connections, so this step is always needed.
4. For **(a)**, set the scenario schedule to *Every day* at 07:00. For **(b)**, copy the custom webhook URL into your form.
5. The toolkit must be reachable from Make's cloud: deploy it, or expose it for testing with a tunnel such as `cloudflared tunnel --url http://localhost:8000`.

> The Make blueprints were written by hand to mirror the n8n flows and have **not** been import-tested on a Make account yet. Module versions or field names may need re-selecting after import.

## Reliability

| Concern | How it is handled |
|---|---|
| **Retries** | HTTP fetches, HubSpot calls: `tenacity` with randomized exponential backoff on network errors, 429 and 5xx (4 attempts). Other 4xx responses fail fast. |
| **Rate limiting / politeness** | `robots.txt` is checked per host and cached; a 404 robots file means allow-all. A minimum delay between requests (`REQUEST_DELAY_SECONDS`), a global concurrency cap (`MAX_CONCURRENCY`), a page cap (`MAX_PAGES`), and an identifying `User-Agent` with a repo URL. Optional `PROXY_URL` for both httpx and Playwright. |
| **A bad row never stops the job** | Parsing: each product card is parsed separately and failures are collected. Storage: each item is written in its own SAVEPOINT, so one DB error rolls back only that row. Runs with some failures end as `partial`, not `failed`. |
| **Snapshot on failure** | When a page or card does not parse, the raw HTML is saved to `data/snapshots/<source>_<timestamp>_<url>.html` and its path is stored in the job's `meta.failures`. |
| **Idempotency** | Leads have a unique key on `(email, sha256(normalized payload))`. A resubmitted form returns the existing lead (`200`, `duplicate: true`). The database constraint also catches two identical requests arriving at the same moment. HubSpot uses *batch upsert by email*, so a retry updates the contact instead of creating a duplicate. Products are unique on `(source, external_id)`. |
| **Run logs** | Every scrape writes a `job_runs` row: status (`queued → running → succeeded/partial/failed`), start and finish time, `duration_ms`, totals, error text, and up to 20 failure samples. Read it at `GET /jobs/{id}`. Logs are structured JSON (`structlog`) with `job_id` on every line. |
| **Alerts never break a scrape** | Notification and Sheet errors are logged; the scrape result stays committed. Email is sent only when every primary channel (Slack, Telegram) fails. First-run "new product" events are stored but not alerted, so the first scrape does not send a message per catalogue item. |
| **Demo mode** | Missing Google or HubSpot credentials switch those integrations to local CSV files plus `would_send` logs. `/health` shows which integrations are live. |

## Configuration

All settings are environment variables (see [`.env.example`](.env.example)). Nothing secret is committed.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://toolkit:toolkit@localhost:5434/toolkit` | Postgres (compose maps it to host port 5434) |
| `REDIS_URL` | `redis://localhost:6379/0` | ARQ queue. Without Redis, the API runs jobs in-process |
| `API_KEY` | `change-me` | Required in the `X-API-Key` header on `POST` endpoints |
| `USER_AGENT` | `PriceMonitorBot/0.1 (+repo URL)` | Identifies the bot to target sites |
| `REQUEST_DELAY_SECONDS` | `1.0` | Minimum gap between requests |
| `MAX_CONCURRENCY` | `4` | Parallel requests cap |
| `MAX_PAGES` | `5` | Listing pages per run |
| `BOOKS_FETCH_DETAILS` | `false` | Also fetch each product page for the exact stock count, category and UPC (one extra request per product) |
| `PROXY_URL` | - | e.g. `http://user:pass@proxy:8000` |
| `RESPECT_ROBOTS_TXT` | `true` | Honour robots.txt |
| `SCHEDULE_HOUR_UTC` / `SCHEDULE_TARGETS` | `6` / `["books"]` | Daily cron in the worker |
| `PRICE_CHANGE_THRESHOLD_PCT` | `0` | Ignore smaller price moves |
| `LEAD_SCORE_THRESHOLD` | `60` | Score at which a lead is qualified and synced |
| `GOOGLE_SERVICE_ACCOUNT_FILE` / `GOOGLE_SHEET_ID` | - | Sheets live mode. Share the sheet with the service-account email |
| `HUBSPOT_TOKEN` | - | Private-app token for HubSpot live mode |
| `SLACK_WEBHOOK_URL` | - | Slack incoming webhook |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | - | Telegram alerts |
| `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASSWORD` `SMTP_FROM` `ALERT_EMAIL_TO` | - | Email fallback (STARTTLS) |

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
        int stock_count
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

## Project layout

```
src/toolkit/
  scraping/      Scraper interface, polite HTTP client, books (httpx+selectolax), quotes (Playwright)
  services/      change detection, job runs, lead pipeline, export, job dispatch
  integrations/  Sheets, HubSpot, Slack/Telegram/SMTP clients + fakes + demo mode, business sinks
  api/           FastAPI app and routers
  worker/        ARQ worker + daily cron
  db/            SQLAlchemy 2.0 async models, session, queries
migrations/      Alembic
workflows/       n8n exports and Make blueprints
tests/           parser tests on saved HTML, respx-mocked APIs, fakes, Testcontainers Postgres
```

## Quality

- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy` (strict, on `src/`)
- `uv run pytest`: parser tests on saved HTML fixtures, respx-mocked HubSpot, Slack and Telegram, fake Sheets and HubSpot clients, API tests on SQLite, and one Testcontainers PostgreSQL integration test (skipped automatically when Docker is not available)
- GitHub Actions runs lint, type-check, tests and a Docker build on every push

## Scope and limits

- The scrape targets are the public practice sites **books.toscrape.com** and **quotes.toscrape.com/js**, which exist to be scraped. Pointing the toolkit at a real site means writing a new parser behind the same `Scraper` interface, and checking that site's terms and robots.txt.
- quotes.toscrape.com has no prices. It shows the Playwright path and new-item detection; each quote is stored as a "product" with the author and tags in `extra`.
- The Google Sheets, HubSpot, Slack, Telegram and SMTP clients are covered by mocked and fake tests. In this repository they have not been run against live accounts; plug in your credentials and check `/health`.

## Roadmap

- [ ] Airtable as an alternative to Google Sheets
- [ ] Pipedrive as an alternative CRM to HubSpot
- [ ] Zapier versions of both workflows
- [ ] Residential or rotating proxy pool, with per-domain proxy rules
- [ ] LLM-assisted extraction for sites without a stable HTML structure
- [ ] Per-competitor price comparison view (match the same product across sites)

## License

MIT
