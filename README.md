# Dascet AI Engine

An AI-powered tool recommendation engine for [Dascet](https://dascet.com) — a Canadian fintech platform helping young Canadians navigate financial products.

## What This Is

Dascet has 200+ curated financial tools in its database. This engine lets a user describe their financial situation in plain language and returns the most relevant tools — not by keyword matching, but by semantic understanding.

It uses embeddings, vector search, and an LLM reasoning layer to bridge the gap between "I have credit card debt and no savings" and the right set of tools to explore.

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
| Embeddings | OpenAI `text-embedding-3-small` |
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

# Run an experiment script
npm run experiment src/experiments/01-first-embedding.ts
```

## Build Status

🟡 **Phase 1 in progress** — Foundations & Concepts

---

Built by [Tomi Salami](https://tomisalami.netlify.app) as part of a self-directed structured AI engineering learning program.
