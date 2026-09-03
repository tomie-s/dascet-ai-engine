import { Hono } from "hono";
import { z } from "zod";
import { NoMatchesError, recommend } from "../lib/recommender.js";

const requestSchema = z.object({
  message: z.string().trim().min(1).max(2_000),
});

export const recommendRoute = new Hono();

recommendRoute.post("/", async (context) => {
  const body: unknown = await context.req.json().catch(() => null);
  const parsed = requestSchema.safeParse(body);

  if (!parsed.success) {
    return context.json(
      { error: "Request body must contain a message between 1 and 2,000 characters." },
      400
    );
  }

  try {
    return context.json(await recommend(parsed.data.message));
  } catch (error) {
    if (error instanceof NoMatchesError) {
      return context.json(
        { error: "No relevant products were found. Try adding more detail." },
        404
      );
    }

    console.error("Recommendation request failed", error);
    return context.json({ error: "The recommendation could not be generated." }, 502);
  }
});
