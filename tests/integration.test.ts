import assert from "node:assert/strict";
import test, { mock } from "node:test";
import Anthropic from "@anthropic-ai/sdk";
import { harness, ROBO, reply, STARTER, submit, toolUse } from "./helpers.js";

/**
 * End-to-end through HTTP: the real route, request validation, and agent
 * loop run together; only Claude and the catalogue search are faked.
 */

process.env.SUPABASE_URL ??= "http://127.0.0.1:54321";
process.env.SUPABASE_SERVICE_ROLE_KEY ??= "test-service-role-key";

const { runAgent } = await import("../src/lib/agent.js");
const { createRecommendRoute, INVALID_REQUEST_MESSAGE } = await import(
  "../src/routes/recommend.js"
);
type AgentDeps = import("../src/lib/agent.js").AgentDeps;

mock.method(console, "log", () => {});

function apiWith(deps: AgentDeps) {
  return createRecommendRoute((turns) => runAgent(turns, deps));
}

async function post(route: ReturnType<typeof apiWith>, body: unknown) {
  const response = await route.request("/", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
  return { status: response.status, text: await response.text() };
}

const ask = (question: string, choices?: string[]) =>
  toolUse("ask_clarifying_question", choices ? { question, choices } : { question });

// --- recommend-now ---

test("a clear request is searched and recommended end to end", async () => {
  const { deps, requests, queries } = harness([
    reply([toolUse("search_tools", { query: "beginner investing" })]),
    reply([submit([STARTER, ROBO])]),
  ]);

  const { status, text } = await post(apiWith(deps), {
    turns: [{ role: "user", content: "I want to start investing" }],
  });

  assert.equal(status, 200);
  assert.deepEqual(JSON.parse(text), {
    type: "recommendation",
    tools: [
      { id: STARTER.id, name: STARTER.name, why: "It may be relevant." },
      { id: ROBO.id, name: ROBO.name, why: "It may be relevant." },
    ],
    explanation: "Options to explore.",
  });
  assert.deepEqual(queries, ["beginner investing"]);
  assert.equal(requests.length, 2);
});

// --- clarify-first ---

test("a vague request is clarified, then the answer is recommended", async () => {
  const question = "What would you like help with?";
  const choices = ["Saving", "Investing"];
  const first = harness([reply([ask(question, choices)])]);

  const firstResponse = await post(apiWith(first.deps), {
    turns: [{ role: "user", content: "help me with money" }],
  });

  assert.equal(firstResponse.status, 200);
  const clarification = JSON.parse(firstResponse.text);
  assert.deepEqual(clarification, { type: "clarification", question, choices });
  assert.deepEqual(first.queries, []);

  // The client sends the whole visible conversation back with the answer.
  const turns = [
    { role: "user", content: "help me with money" },
    { role: "assistant", content: clarification.question },
    { role: "user", content: "Investing" },
  ];
  const second = harness([
    reply([toolUse("search_tools", { query: "investing for beginners" })]),
    reply([submit([STARTER])]),
  ]);

  const secondResponse = await post(apiWith(second.deps), { turns });

  assert.equal(secondResponse.status, 200);
  assert.equal(JSON.parse(secondResponse.text).type, "recommendation");
  assert.deepEqual(second.requests[0].messages, turns);
  assert.deepEqual(second.queries, ["investing for beginners"]);
});

// --- provider failures ---

test("a Claude API failure returns a generic 502 without leaking secrets", async (t) => {
  const secret = "sk-ant-sentinel-should-not-leak";
  const logged: unknown[][] = [];
  t.mock.method(console, "error", (...args: unknown[]) => {
    logged.push(args);
  });
  const { deps } = harness([]);
  deps.createMessage = async () => {
    throw Anthropic.APIError.generate(
      500,
      { type: "error", error: { type: "api_error", message: "Internal server error" } },
      undefined,
      new Headers({ "x-api-key": secret })
    );
  };

  const { status, text } = await post(apiWith(deps), {
    turns: [{ role: "user", content: "I want to start investing" }],
  });

  assert.equal(status, 502);
  assert.deepEqual(JSON.parse(text), { error: "The recommendation could not be generated." });
  assert.ok(!text.includes(secret));
  assert.equal(logged.length, 1);
  assert.ok(!JSON.stringify(logged).includes(secret));
});

test("a catalogue search failure returns a generic 502", async (t) => {
  const logged: unknown[][] = [];
  t.mock.method(console, "error", (...args: unknown[]) => {
    logged.push(args);
  });
  const { deps } = harness([reply([toolUse("search_tools", { query: "investing" })])]);
  deps.searchTools = async () => {
    throw new Error("Vector search failed: connection refused");
  };

  const { status, text } = await post(apiWith(deps), {
    turns: [{ role: "user", content: "I want to start investing" }],
  });

  assert.equal(status, 502);
  assert.deepEqual(JSON.parse(text), { error: "The recommendation could not be generated." });
  assert.ok(!text.includes("Vector search failed"));
  assert.match(JSON.stringify(logged), /Vector search failed/);
});

// --- validation stops costs ---

test("an invalid request returns 400 without calling the model or search", async () => {
  const { deps, requests, queries } = harness([]);

  const { status, text } = await post(apiWith(deps), {
    turns: [
      { role: "user", content: "hi" },
      { role: "assistant", content: "What?" },
    ],
  });

  assert.equal(status, 400);
  assert.deepEqual(JSON.parse(text), { error: INVALID_REQUEST_MESSAGE });
  assert.equal(requests.length, 0);
  assert.equal(queries.length, 0);
});
