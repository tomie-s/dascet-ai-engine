# experiments/

This folder contains learning scripts from Phase 1 and Phase 2.

These are **not** production code. They exist to explore how the technology works
before building the real system. Each file is numbered in the order it was written.

| File | What it does |
|---|---|
| `01-first-embedding.ts` | Calls the OpenAI embedding API and logs the raw vector |
| `02-similarity.ts` | Embeds 3 strings and computes cosine similarity scores |

Run any script with:
```bash
npm run experiment src/experiments/<filename>.ts
