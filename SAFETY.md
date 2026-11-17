# Safety, privacy, and operations

This document covers what the Dascet AI Engine does with user data, which safeguards it has, what it does not do, and how to recover when something fails. How recommendation quality is measured is in [EVALUATION.md](EVALUATION.md).

## 1. What this is, and what it is not

The engine is a learning project. Given a plain-language description of someone's financial situation, it returns products from Dascet's catalogue that may be relevant, with a short neutral explanation of each. It runs as a standalone sandbox, not as part of a live app.

It is **not financial advice**. The engine is built to inform, not to decide:

- It never tells the user what to do with their money, never ranks products, and never calls one "best" (`SAFETY_RULES` in `src/lib/prompt.ts`). The user makes every choice.
- It only describes products returned by its own catalogue search. It does not know the user's full finances, and it cannot judge whether a product suits them.
- Rates, fees, and eligibility come from a catalogue snapshot taken in July 2026 and may be out of date. Recommendations remind the user to confirm material terms with the provider.
- For debt requests, it includes non-profit credit counselling alongside other products. It does not replace a counsellor or a licensed adviser.

A client that shows these responses to people should present them the same way: as starting points to compare, not as advice.

## 2. Data handling

The API has no accounts and keeps no conversation state. Each request carries the whole visible conversation, at most three turns, and nothing is stored after the response is sent.

| Where | What it receives | Code |
|---|---|---|
| **Anthropic** (Claude Haiku 5.5) | The conversation as sent by the client (user turns, and the assistant turn the client sends back), the system prompt, and the search results. Only the system prompt is marked for prompt caching | `src/lib/agent.ts` |
| **Voyage AI** (`voyage-3-lite`) | The search query the agent writes, with a fixed prefix (up to 300 characters). It is not the raw user message, but it can include details the user gave, such as their bank or situation | `searchTools` in `src/lib/recommender.ts` |
| **Supabase** | The query embedding (a list of numbers) and product IDs. No text from the user | `searchTools` in `src/lib/recommender.ts` |
| **Application logs** (Railway) | One line of counts per request (model calls, searches, tokens), and an error's name and message when a request fails. User messages are never logged | `src/lib/agent.ts`, `src/routes/recommend.ts`, `src/app.ts` |
| **Server memory** | The client IP of recent requests, for rate limiting. Held until the daily window resets or the server restarts or sleeps (at most about 24 hours), and never written to disk | `src/lib/rate-limit.ts` |

What this means in practice:

- **Anything a user types is sent to Anthropic.** If a user volunteers a Social Insurance Number, income, or account number, it reaches Anthropic as part of the conversation, and parts of it may reach Voyage AI in the agent's search query. The engine never asks for this information (decision rule 5 in the system prompt), and the eval checks that a volunteered SIN is not repeated in the response (case adv-07), but the engine does not remove it before calling the providers.
- **The platform sees requests too.** Railway terminates HTTPS in front of the app and can keep its own request logs, outside the application's control.
- **The eval set contains no real user data.** All cases are hand-written; the SIN in adv-07 is a widely published sample number.

Each provider's handling of API data is set by its own policy and the account's settings:

- Anthropic: <https://www.anthropic.com/legal/privacy>
- Voyage AI: <https://www.voyageai.com/privacy>
- Supabase: <https://supabase.com/privacy>
- Railway: <https://railway.com/legal/privacy>

## 3. Safeguards

| Risk | Safeguard | Where |
|---|---|---|
| Oversized or malformed requests | Bodies over 16 KB are rejected unread (`413`); turns are validated with Zod (`400`) | `src/routes/recommend.ts`, `src/lib/agent.ts` |
| Abuse and runaway spend | 5 requests a minute per client IP and 300 a day overall (`429` with `Retry-After`), in production. Each request is capped at 4 model calls, 2 searches, and 4,096 output tokens per call. The Anthropic workspace has a monthly spend limit | `src/lib/rate-limit.ts`, `src/lib/tools.ts` |
| Made-up products | Submitted products must come from this request's searches, with the exact ID and name, or the model is asked to correct itself | `validateRecommendation` |
| Prompt injection | User messages, assistant turns, and search results are treated as data. Assistant turns from the client must have the shape of a real clarifying question (up to 200 characters, ending in "?"). Tool calls are validated, and unknown tools are rejected | `src/lib/prompt.ts`, `src/lib/agent.ts`, `src/lib/tools.ts` |
| Unsafe financial framing | `SAFETY_RULES`: neutral wording, no ranking, counselling first for debt, loans described as restructuring debt with variable costs | `src/lib/prompt.ts` |
| Leaking secrets or internals | Errors return generic messages; logs keep only an error's name and message; config errors name variables, never values; dev-only usage counts are refused in production | `src/app.ts`, `src/routes/recommend.ts`, `src/config.ts` |

The adversarial eval cases and their results are in [EVALUATION.md](EVALUATION.md), sections 2, 4, and 5. The regression check (`npm run eval:check`) requires grounding, safety, and the no-leak check to pass for every case.

## 4. Limitations

Limits of the engine itself:

- **Canada first.** Whenever any Canadian product matches, products unavailable in Canada are dropped, so a user elsewhere cannot get products for their country.
- **English.** The prompt and checks are written for English. Replies to French requests are not tested.
- **A dated catalogue.** The catalogue is a July 2026 snapshot. Products, rates, and fees may have changed.
- **Opinions in the catalogue text.** Many product descriptions contain phrases the engine is told not to use ("worth a serious look", "hard to beat", "Competitive"). The agent reads them in search results, which may contribute to its occasional wording slips. They have not been cleaned.
- **Products named in text.** The engine checks the products it returns, but not product names inside its explanations or questions. A prompt rule and the eval check cover these, and rare slips are possible.
- **In-memory rate limits.** Counters reset when the server restarts or wakes from sleep, and the per-IP limit relies on the `X-Real-IP` header set by Railway's edge.
- **No Voyage AI spend cap.** The Anthropic workspace has a monthly limit; Voyage AI usage is bounded only by the rate limits.

Limits of the evaluation (eval set size, one author, few runs per setting, word-based checks) are in [EVALUATION.md, section 6](EVALUATION.md#6-limitations).

## 5. Failure modes and recovery

Start with `railway logs`. Failed requests log `Recommendation request failed` with the error's name and message, and the deployment's logs show startup errors.

| Symptom | Likely cause | Recovery |
|---|---|---|
| `429` for every client | The overall limit of 300 requests a day was reached | Wait for the time in `Retry-After`, or redeploy to reset the counters. Look at the logs for unusual traffic first |
| `429` for one client | That client sent more than 5 requests in a minute | Wait for the time in `Retry-After` |
| `502` on every request | The Anthropic workspace reached its monthly spend limit, or the API key expired or was revoked | Raise the limit in the Anthropic Console, or check the key's expiry there and rotate it ([README](README.md#rotating-the-anthropic-api-key)) |
| `502` on requests that search; clarifying questions still work | Voyage AI rejected the embedding (rate limit, billing, or key), or Supabase is unavailable or paused | Check the Voyage AI dashboard (billing, usage) and the Supabase project's status; restore the project if it was paused |
| `502` after a clarifying question was answered | The agent could not finish within its call limit | Usually a one-off; the user can send the request again. Repeated failures for one kind of request belong in the eval set |
| The service does not start or keeps restarting | A required variable is missing or invalid, or `EVAL_INCLUDE_USAGE` is set in production | The log names the variable without its value. Fix it in Railway's **Variables** tab, which redeploys |
| The first request after a quiet period takes about 2 seconds longer | The service was asleep (serverless setting) | Expected; no action |
| A deploy breaks a working service | A code or configuration change | Roll back to the previous deployment, then run the smoke test ([README](README.md#redeploy-logs-and-rollback)) |
| Recommendations get worse after a prompt, tool, retrieval, or catalogue change | A regression | Run `npm run eval:check -- --paid` against a local server; it names the cases that got worse ([EVALUATION.md, section 7](EVALUATION.md#regression-check)) |

After any recovery, run `npm run smoke -- <url>` (add `--skip-paid` for the free checks only).
