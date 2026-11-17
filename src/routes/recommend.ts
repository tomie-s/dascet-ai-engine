import { Hono } from "hono";
import { bodyLimit } from "hono/body-limit";
import { z } from "zod";
import { type AgentResult, runAgent, type Turn, turnsSchema } from "../lib/agent.js";

const requestSchema = z.object({ turns: turnsSchema });

export const INVALID_REQUEST_MESSAGE =
  "Request body must contain 1 to 3 turns that alternate between user and assistant, " +
  "start and end with the user, and keep user messages between 1 and 2,000 characters " +
  "and assistant turns to one question of up to 200 characters.";

/** The largest valid body is about 13 KB (3-byte characters at every limit); anything over this is rejected unread. */
export const MAX_BODY_BYTES = 16 * 1_024;

export const BODY_TOO_LARGE_MESSAGE = "Request body is too large.";

export type RunAgentFn = (turns: Turn[]) => Promise<AgentResult>;

/**
 * The agent is injectable so tests can exercise every response path without paid calls.
 * EVAL_INCLUDE_USAGE=1 adds per-run token counts to each response for local evaluation
 * runs; production leaves it unset.
 */
export function createRecommendRoute(
  runAgentFn: RunAgentFn = (turns) =>
    runAgent(turns, undefined, { includeUsage: process.env.EVAL_INCLUDE_USAGE === "1" })
) {
  const route = new Hono();

  const limitBody = bodyLimit({
    maxSize: MAX_BODY_BYTES,
    onError: (context) => context.json({ error: BODY_TOO_LARGE_MESSAGE }, 413),
  });

  route.post("/", limitBody, async (context) => {
    const body: unknown = await context.req.json().catch(() => null);
    const parsed = requestSchema.safeParse(body);

    if (!parsed.success) {
      return context.json({ error: INVALID_REQUEST_MESSAGE }, 400);
    }

    try {
      return context.json(await runAgentFn(parsed.data.turns));
    } catch (error) {
      // Log only the name and message: provider SDK errors can carry request details.
      const { name, message } =
        error instanceof Error ? error : { name: "UnknownError", message: String(error) };
      console.error("Recommendation request failed", { name, message });
      return context.json({ error: "The recommendation could not be generated." }, 502);
    }
  });

  return route;
}

export const recommendRoute = createRecommendRoute();
