# Dascet AI Engine

An AI-powered tool recommendation engine for [Dascet](https://dascet.com) — a Canadian fintech platform helping young Canadians navigate financial products.

## What This Is

Dascet has 200+ curated financial tools in its database. This engine lets a user describe their financial situation in plain language and returns the most relevant tools — not by keyword matching, but by semantic understanding.

It uses embeddings, vector search, and an LLM reasoning layer to bridge the gap between "I have credit card debt and no savings" and the right set of tools to explore.

The project uses its own self-contained Supabase database containing a July 2026 snapshot of the financial-tools catalogue.

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
| LLM | Anthropic Claude |
| Vector Store | Supabase + pgvector |
| Validation | Zod |
| Deployment | Railway |

## Project Structure

```
experiments/          # Phase 1–3 learning scripts (not production code)
src/
├── lib/              # Shared utilities (embeddings, Supabase, prompts)
├── routes/           # Hono API route handlers
└── server.ts         # API entry point
supabase/migrations/ # Standalone learning-database migrations
```

## Getting Started

```bash
# Install dependencies
npm install

# Copy env file and fill in your keys
cp .env.example .env

# Create the standalone catalogue schema by running this migration in Supabase
# supabase/migrations/202607220001_create_financial_tools.sql

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

The regression suite checks catalogue integrity, embedding coverage and
dimensions, and pgvector retrieval without making paid embedding or LLM calls.

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
| `search_tools` | Vector search over the catalogue (up to five products, Canadian-available first) |
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

### Service settings

| Setting | Value | Why |
|---|---|---|
| Healthcheck path | `/health` | Railway waits for a `200` before switching traffic to a new deployment |
| Restart policy | On failure, 10 retries | Recovers from crashes without restarting a deliberate exit |

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

## Build Status

✅ **Phase 5 complete** — Deployment & MLOps: a Docker container on Railway with health checks, graceful shutdown, and a repeatable smoke test

---

Built by [Tomi Salami](https://tomisalami.netlify.app) as part of a self-directed structured AI engineering learning program.
