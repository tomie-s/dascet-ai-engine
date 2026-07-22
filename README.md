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
src/
├── experiments/     # Phase 1 & 2 learning scripts (not production code)
├── lib/             # Shared utilities (embeddings, supabase client, etc.)
├── routes/          # Hono API route handlers
└── server.ts        # API entry point
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
```

The regression suite checks catalogue integrity, embedding coverage and
dimensions, and pgvector retrieval without making paid embedding or LLM calls.

## Build Status

🟡 **Phase 3 in progress** — Prompt Engineering the Recommender

---

Built by [Tomi Salami](https://tomisalami.netlify.app) as part of a self-directed structured AI engineering learning program.
