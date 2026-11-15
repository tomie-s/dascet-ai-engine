# Dascet AI Engine

An AI-powered product recommendation engine for [Dascet](https://dascet.com) — a Canadian fintech platform helping young Canadians navigate financial products.

## What This Is

Dascet has 200+ curated financial products in its database. This engine lets a user describe their financial situation in plain language and returns the most relevant products — not by keyword matching, but by semantic understanding.

It uses embeddings, vector search, and an LLM reasoning layer to bridge the gap between "I have credit card debt and no savings" and the right set of products to explore.

The project uses its own self-contained Supabase database containing a July 2026 snapshot of the financial products catalogue.

## What I'm Learning

This project is a hands-on learning exercise covering:

- **Embeddings** — converting text into vectors for semantic similarity search
- **RAG (Retrieval-Augmented Generation)** — retrieving relevant context before generating a response
- **Prompt Engineering** — writing structured, reliable prompts for consistent LLM output
- **Agentic Workflows** — multi-step reasoning with tool use and clarifying questions
- **Deployment & MLOps** — shipping and observing a real AI API
- **Evaluation** — measuring whether the system is actually working well
- **Governance & Security** — rate limiting, prompt injection defence, safe AI output

## Tech Stack

| Layer | Technology |
|---|---|
| Language | TypeScript |
| API | Hono |
| Embeddings | Voyage AI `voyage-3-lite` |
| LLM | Anthropic Claude Haiku 5.5 (agent) |
| Vector Store | Supabase + pgvector |
| Validation | Zod |
| Deployment | Railway |
| Evaluation | Python 3.12+ with pytest and httpx (`evals/`) |

## Project Structure

```
evals/                # Python evaluation harness, eval set, and results (see EVALUATION.md)
experiments/          # Phase 1–3 learning scripts (not production code)
scripts/              # Smoke test and the Phase 1–2 database checks
src/
├── lib/              # Agent loop, tools, prompts, retrieval, and the Supabase client
├── routes/           # Hono API route handlers
└── server.ts         # API entry point
supabase/migrations/  # Standalone learning-database migrations
```

## Getting Started

```bash
# Install dependencies
npm install

# Copy env file and fill in your keys
cp .env.example .env

# Create the standalone catalogue by running the migrations in
# supabase/migrations/ in order, in the Supabase SQL editor

# Run an experiment script
npm run experiment experiments/01-embed-one-tool.ts

# Run the read-only Phase 1–2 regression suite
npm run test:phase1-2

# Run the zero-cost offline suite: prompt, config, API, agent loop, and
# end-to-end HTTP integration tests (Claude and catalogue search are faked)
npm test

# Run everything: the database checks plus the offline suite
npm run test:all

# Start the recommendation API on http://localhost:3000
npm run dev

# In another terminal, request a recommendation (makes paid Voyage AI and Claude calls)
curl -X POST http://localhost:3000/recommend \
  -H 'content-type: application/json' \
  -d '{"turns":[{"role":"user","content":"I am new to investing and want to start small"}]}'
```

The Phase 1–2 database checks verify catalogue integrity, embedding coverage
and dimensions, and pgvector retrieval without making paid embedding or LLM
calls.

Code quality uses Biome:

| Command | Purpose |
| --- | --- |
| `npm run lint:check` | Check lint rules without changing files |
| `npm run lint` | Apply safe lint fixes |
| `npm run format:check` | Check formatting without changing files |
| `npm run format` | Format files |
| `npm run fix:check` | Check lint, formatting, and import organization |
| `npm run lint:fix` | Apply safe fixes, formatting, and import organization |
| `npm run staged` | Apply Biome fixes to staged files |
| `npm run type-check` | Run all TypeScript checks (alias for `typecheck`) |

## API

The server validates its configuration at startup and exits with a list of
missing or invalid variables (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
`VOYAGE_API_KEY`, `ANTHROPIC_API_KEY`, optional `PORT`).

### `GET /health`

Returns `200` `{"status":"ok"}`.

### `POST /recommend`

Recommendations come from a bounded agent loop. Claude
(`claude-haiku-5-5`) decides whether to search the catalogue, ask one
clarifying question, or recommend, using exactly three tools:

| Tool | What it does |
|---|---|
| `search_tools` | Vector search over the catalogue (up to five products; only Canadian-available ones when any match) |
| `ask_clarifying_question` | Asks the user one short question, with optional choices. Ends the run |
| `submit_recommendation` | Returns products found by this run's searches. Ends the run |

Every tool call is validated in code: unknown tools, invalid input, and
products that weren't returned by a search are rejected, and the model is
asked to correct itself.

**Limits per request:** at most 4 model calls, 2 searches, 4,096 output
tokens per call, and 1 clarifying question per conversation. If the agent
can't finish, it returns a fixed clarifying question instead (or a `502`
if one was already asked).

Request body (JSON): the visible conversation so far, as 1–3 turns that
alternate between `user` and `assistant` and start and end with the user.
User turns are 1–2,000 characters; assistant turns are 1–500 characters.

```json
{ "turns": [{ "role": "user", "content": "help me with money" }] }
```

The server keeps no conversation state. To answer a clarifying question,
send the whole conversation back:

```json
{
  "turns": [
    { "role": "user", "content": "help me with money" },
    { "role": "assistant", "content": "What would you like help with?" },
    { "role": "user", "content": "Investing" }
  ]
}
```

Only text is accepted from the client. Searches run on the server on every
request, and client-supplied products or tool results are ignored.

Success (`200`) is one of two shapes, told apart by `type`:

```json
{
  "type": "recommendation",
  "tools": [
    { "id": "<catalogue id>", "name": "<product name>", "why": "<reason it may be relevant>" }
  ],
  "explanation": "<overall summary>"
}
```

```json
{
  "type": "clarification",
  "question": "What would you like help with?",
  "choices": ["Saving", "Investing", "Paying down debt", "Building credit", "Budgeting"]
}
```

`choices` is optional (2–5 short options).

Errors are always JSON in the form `{"error": "<message>"}`:

| Status | When |
|---|---|
| `400` | The body is missing or malformed, or `turns` breaks the rules above |
| `404` | The route doesn't exist |
| `502` | A provider (Voyage AI, Supabase, Claude) failed, or the agent couldn't finish after a clarification. The details are logged on the server and never returned |

Each request logs one line of counts (model calls, searches, input, output,
and cache tokens) and never the user's messages.

When the server is started with `EVAL_INCLUDE_USAGE=1` (local evaluation
only), each response from a finished run also includes a `usage` object with
the model and the same counts. Production never sets it.

## Deployment

The API runs on [Railway](https://railway.com) as a Docker container built
from the root `Dockerfile` (Node 26, production dependencies only, non-root
user). Deploys are made from a local checkout with the Railway CLI.

### Environment variables

Set these in the Railway service's **Variables** tab. They are injected at
runtime and are never part of the image.

| Variable | Required | Notes |
|---|---|---|
| `SUPABASE_URL` | Yes | Supabase project holding the catalogue |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Server-side key; never expose to a client |
| `VOYAGE_API_KEY` | Yes | Voyage AI embeddings |
| `ANTHROPIC_API_KEY` | Yes | Use a key from a dedicated Anthropic Console workspace with a monthly spend limit |
| `RAILWAY_DEPLOYMENT_DRAINING_SECONDS` | Yes, set to `10` | Seconds between `SIGTERM` and `SIGKILL` on redeploy. Railway's default is `0`, which skips graceful shutdown; `10` matches the server's shutdown timeout |
| `PORT` | No | Set by Railway automatically; do not add it |
| `AGENT_MODEL` | No | Local evaluation only; overrides the agent model (default `claude-haiku-5-5`). Do not add it |
| `EVAL_INCLUDE_USAGE` | No | Local evaluation only; `1` adds token counts to `/recommend` responses. Do not add it |

### Service settings

| Setting | Value | Why |
|---|---|---|
| Healthcheck path | `/health` | Railway waits for a `200` before switching traffic to a new deployment |
| Restart policy | On failure, 10 retries | Recovers from crashes without restarting a deliberate exit |
| Serverless (app sleeping) | On | Saves credit while idle. The first request after a quiet period takes about 2 seconds longer (measured 2026-11-15), well within the smoke test's 10-second timeout |

Draining time is set with the `RAILWAY_DEPLOYMENT_DRAINING_SECONDS`
variable above ([deployment teardown](https://docs.railway.com/deployments/deployment-teardown)).

### First deploy

```bash
npm install -g @railway/cli   # or: brew install railway
railway login                 # opens the browser
railway link                  # pick the project and service
railway up                    # uploads this folder, builds the Dockerfile, deploys
```

Then run `railway domain` to generate the public `*.up.railway.app` domain
(it creates one if none exists, otherwise prints the existing one).
`railway up` respects `.gitignore`, so `.env` is never uploaded.

### Smoke test

```bash
# Free checks: health, unknown route, request validation
npm run smoke -- https://<your-domain> --skip-paid

# Adds one real recommendation request (paid Voyage AI and Claude calls)
npm run smoke -- https://<your-domain>
```

The same script works against a local server or container
(`npm run smoke -- http://localhost:3000`). It prints statuses and response
types only and exits `1` if any check fails.

### Redeploy, logs, and rollback

- **Redeploy:** run `railway up` again. The old deployment receives `SIGTERM`
  and drains before it stops.
- **Logs:** `railway logs`, or the deployment's **Logs** tab in the dashboard.
- **Rollback:** in the service's **Deployments** list, open a previous
  successful deployment's menu and choose **Rollback**. Then run the smoke test.

### Rotating the Anthropic API key

Console keys have an expiry date. Before it passes: create a new key in the
same Anthropic workspace, replace `ANTHROPIC_API_KEY` in Railway's
**Variables** (Railway redeploys automatically), run the smoke test, then
delete the old key.

## Evaluation

Retrieval and recommendation quality are measured separately against 36 hand-written requests (`evals/cases.jsonl`), with deterministic checks as the main signal and no LLM judge. End-to-end figures are the mean of three runs:

| Measure | Before Phase 6 tuning | After |
|---|---|---|
| Responses that follow the wording rules | 0.65 | 0.95 |
| Retrieval: an expected product in the top 5 (user's own words) | 0.79 | 0.89 |
| End to end: an expected product returned | 0.95 | 0.95 |
| Grounded in the catalogue, valid schema, safety checks | 1.0 | 1.0 |

A full 36-request run costs about US$0.03 on Claude Haiku 5.5. Claude Sonnet 5.5 scored about the same at about 16 times the cost per request, so the agent stays on Haiku. The method, every experiment, the failure analysis, and the known limitations are in [EVALUATION.md](EVALUATION.md).

Before changing prompts, tool descriptions, retrieval settings, or catalogue text, run the regression check. It exits with an error and names the cases that got worse when a score drops below the accepted reference:

```bash
npm run eval:setup            # once
npm run eval:check            # free: retrieval and harness checks
npm run eval:check -- --paid  # also one end-to-end run against `npm run dev` (paid, about US$0.03)
```

## Build Status

✅ **Phase 6 complete** — Evaluation & Optimization: a Python evaluation harness and measured baseline, prompt and catalogue tuning against it, and a one-command regression check

---

Built by [Tomi Salami](https://tomisalami.netlify.app) as part of a self-directed structured AI engineering learning program.
