import assert from "node:assert/strict";
import test from "node:test";
import { Hono } from "hono";
import { createRateLimiter, RATE_LIMIT_MESSAGE, type RateLimits } from "../src/lib/rate-limit.js";

const LIMITS: RateLimits = {
  perClient: { limit: 2, windowMs: 60_000 },
  global: { limit: 3, windowMs: 86_400_000 },
};

/** A tiny app behind the limiter, with a clock the test controls. */
function limitedApp(limits = LIMITS) {
  const clock = { time: 1_000_000 };
  const app = new Hono();
  app.use("*", createRateLimiter({ limits, now: () => clock.time }));
  app.post("/", (context) => context.json({ ok: true }));
  const send = (ip = "203.0.113.1") =>
    app.request("/", { method: "POST", headers: { "x-real-ip": ip } });
  return { clock, send };
}

test("allows requests up to the per-client limit, then returns a JSON 429", async () => {
  const { send } = limitedApp();

  assert.equal((await send()).status, 200);
  assert.equal((await send()).status, 200);

  const limited = await send();
  assert.equal(limited.status, 429);
  assert.deepEqual(await limited.json(), { error: RATE_LIMIT_MESSAGE });
  assert.equal(limited.headers.get("Retry-After"), "60");
});

test("Retry-After counts down to the end of the window", async () => {
  const { clock, send } = limitedApp();
  await send();
  await send();

  clock.time += 45_500;
  assert.equal((await send()).headers.get("Retry-After"), "15");
});

test("the per-client limit resets when the window ends", async () => {
  const { clock, send } = limitedApp();
  await send();
  await send();
  assert.equal((await send()).status, 429);

  clock.time += 60_000;
  assert.equal((await send()).status, 200);
});

test("clients are counted separately", async () => {
  const { send } = limitedApp();
  await send("203.0.113.1");
  await send("203.0.113.1");

  assert.equal((await send("203.0.113.1")).status, 429);
  assert.equal((await send("203.0.113.2")).status, 200);
});

test("the global limit applies across all clients", async () => {
  const { send } = limitedApp();
  await send("203.0.113.1");
  await send("203.0.113.2");
  await send("203.0.113.3");

  const limited = await send("203.0.113.4");
  assert.equal(limited.status, 429);
  assert.deepEqual(await limited.json(), { error: RATE_LIMIT_MESSAGE });
  assert.equal(limited.headers.get("Retry-After"), "86400");
});

test("rejected requests are not counted", async () => {
  const { clock, send } = limitedApp({
    perClient: { limit: 1, windowMs: 60_000 },
    global: { limit: 2, windowMs: 86_400_000 },
  });
  await send("203.0.113.1");
  assert.equal((await send("203.0.113.1")).status, 429);
  assert.equal((await send("203.0.113.1")).status, 429);

  // The two rejections did not use up the global limit.
  assert.equal((await send("203.0.113.2")).status, 200);

  clock.time += 86_400_000;
  assert.equal((await send("203.0.113.1")).status, 200);
});
