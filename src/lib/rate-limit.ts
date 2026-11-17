import { getConnInfo } from "@hono/node-server/conninfo";
import type { Context, MiddlewareHandler } from "hono";

type WindowLimit = { limit: number; windowMs: number };

export type RateLimits = { perClient: WindowLimit; global: WindowLimit };

/**
 * Per client: 5 requests a minute. Global: 300 a day across all clients, the
 * spend backstop when client keys can be rotated. Counters live in memory, so
 * they reset when the server restarts or wakes from sleep.
 */
export const RATE_LIMITS: RateLimits = {
  perClient: { limit: 5, windowMs: 60_000 },
  global: { limit: 300, windowMs: 24 * 60 * 60 * 1_000 },
};

export const RATE_LIMIT_MESSAGE = "Too many requests. Try again later.";

type Window = { count: number; resetAt: number };

export type RateLimiterOptions = {
  limits?: RateLimits;
  now?: () => number;
  clientKey?: (context: Context) => string;
};

/** Railway's edge sets X-Real-IP; the socket address covers local runs. */
function defaultClientKey(context: Context): string {
  const realIp = context.req.header("x-real-ip")?.trim();
  if (realIp) return realIp;
  try {
    return getConnInfo(context).remote.address ?? "unknown";
  } catch {
    return "unknown";
  }
}

/**
 * Fixed-window limiter. A request is counted only when it is allowed, so
 * rejected requests cannot grow the client map past the global limit.
 */
export function createRateLimiter({
  limits = RATE_LIMITS,
  now = Date.now,
  clientKey = defaultClientKey,
}: RateLimiterOptions = {}): MiddlewareHandler {
  let global: Window = { count: 0, resetAt: 0 };
  const clients = new Map<string, Window>();

  function current(window: Window | undefined, limit: WindowLimit, time: number): Window {
    return window && window.resetAt > time ? window : { count: 0, resetAt: time + limit.windowMs };
  }

  return async (context, next) => {
    const time = now();
    if (global.resetAt <= time) clients.clear();
    global = current(global, limits.global, time);

    const key = clientKey(context);
    const client = current(clients.get(key), limits.perClient, time);

    const blocked =
      global.count >= limits.global.limit
        ? global
        : client.count >= limits.perClient.limit
          ? client
          : undefined;

    if (blocked) {
      context.header("Retry-After", String(Math.ceil((blocked.resetAt - time) / 1_000)));
      return context.json({ error: RATE_LIMIT_MESSAGE }, 429);
    }

    global.count += 1;
    client.count += 1;
    clients.set(key, client);
    await next();
  };
}
