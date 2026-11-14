import assert from "node:assert/strict";
import test from "node:test";
import { ConfigError, loadConfig } from "../src/config.js";

const validEnv = {
  SUPABASE_URL: "http://127.0.0.1:54321",
  SUPABASE_SERVICE_ROLE_KEY: "test-service-role-key",
  VOYAGE_API_KEY: "test-voyage-key",
  ANTHROPIC_API_KEY: "test-anthropic-key",
};

function configIssues(env: NodeJS.ProcessEnv): string[] {
  try {
    loadConfig(env);
  } catch (error) {
    assert.ok(error instanceof ConfigError);
    return error.issues;
  }
  assert.fail("Expected loadConfig to throw a ConfigError");
}

test("valid environment loads with default port", () => {
  assert.deepEqual(loadConfig(validEnv), {
    supabaseUrl: validEnv.SUPABASE_URL,
    supabaseServiceRoleKey: validEnv.SUPABASE_SERVICE_ROLE_KEY,
    voyageApiKey: validEnv.VOYAGE_API_KEY,
    anthropicApiKey: validEnv.ANTHROPIC_API_KEY,
    port: 3000,
  });
});

test("explicit port is used", () => {
  assert.equal(loadConfig({ ...validEnv, PORT: "8080" }).port, 8080);
});

test("empty environment reports every required variable", () => {
  assert.deepEqual(configIssues({}), [
    "SUPABASE_URL is required",
    "SUPABASE_SERVICE_ROLE_KEY is required",
    "VOYAGE_API_KEY is required",
    "ANTHROPIC_API_KEY is required",
  ]);
});

test("blank values count as missing", () => {
  assert.deepEqual(configIssues({ ...validEnv, VOYAGE_API_KEY: "   " }), [
    "VOYAGE_API_KEY is required",
  ]);
});

for (const port of ["abc", "0", "70000", "80.5"]) {
  test(`rejects PORT=${port}`, () => {
    const issues = configIssues({ ...validEnv, PORT: port });
    assert.equal(issues.length, 1);
    assert.match(issues[0], /^PORT is invalid/);
  });
}

test("rejects a malformed SUPABASE_URL", () => {
  const issues = configIssues({ ...validEnv, SUPABASE_URL: "not-a-url" });
  assert.equal(issues.length, 1);
  assert.match(issues[0], /^SUPABASE_URL is invalid/);
});

test("error message never includes secret values", () => {
  const secret = "sk-sentinel-should-not-leak";
  assert.throws(
    () => loadConfig({ ...validEnv, ANTHROPIC_API_KEY: secret, SUPABASE_URL: secret, PORT: "abc" }),
    (error) => {
      assert.ok(error instanceof ConfigError);
      assert.equal(error.issues.length, 2);
      assert.ok(!error.message.includes(secret));
      return true;
    }
  );
});
