import assert from "node:assert/strict";
import test from "node:test";

process.env.SUPABASE_URL ??= "http://127.0.0.1:54321";
process.env.SUPABASE_SERVICE_ROLE_KEY ??= "test-service-role-key";

const { app } = await import("../src/app.js");

test("root describes the API", async () => {
  const response = await app.request("/");

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    name: "Dascet AI Engine",
    status: "running",
    endpoints: {
      health: "GET /health",
      recommend: "POST /recommend",
    },
  });
});

test("health endpoint reports success", async () => {
  const response = await app.request("/health");

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: "ok" });
});

for (const testCase of [
  { name: "empty message", body: JSON.stringify({ message: "   " }) },
  { name: "missing message", body: JSON.stringify({}) },
  { name: "malformed JSON", body: "{" },
  { name: "overlong message", body: JSON.stringify({ message: "x".repeat(2_001) }) },
]) {
  test(`recommend rejects ${testCase.name}`, async () => {
    const response = await app.request("/recommend", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: testCase.body,
    });

    assert.equal(response.status, 400);
    assert.deepEqual(await response.json(), {
      error: "Request body must contain a message between 1 and 2,000 characters.",
    });
  });
}
