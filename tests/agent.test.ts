import assert from "node:assert/strict";
import test, { mock } from "node:test";
import {
  harness,
  lastToolResult,
  product,
  ROBO,
  reply,
  STARTER,
  submit,
  thinking,
  toolUse,
  userTurn,
} from "./helpers.js";

process.env.SUPABASE_URL ??= "http://127.0.0.1:54321";
process.env.SUPABASE_SERVICE_ROLE_KEY ??= "test-service-role-key";

const { AgentError, FALLBACK_CLARIFICATION, runAgent, TOOL_REMINDER } = await import(
  "../src/lib/agent.js"
);
const { AGENT_MODEL, AGENT_TOOLS, AGENT_LIMITS } = await import("../src/lib/tools.js");
const { AGENT_SYSTEM_PROMPT } = await import("../src/lib/prompt.js");
type Turn = import("../src/lib/agent.js").Turn;

// The agent logs one line of counts per run; keep test output quiet.
const logMock = mock.method(console, "log", () => {});

// --- the happy paths ---

test("a clear request searches and recommends without clarifying", async () => {
  const { deps, queries, requests } = harness([
    reply([thinking, toolUse("search_tools", { query: "beginner investing" })]),
    reply([submit([STARTER, ROBO])]),
  ]);

  const result = await runAgent([userTurn("I want to start investing")], deps);

  assert.deepEqual(result, {
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

test("a vague request returns the model's clarifying question", async () => {
  const { deps, queries } = harness([
    reply([
      toolUse("ask_clarifying_question", {
        question: "What would you like help with?",
        choices: ["Saving", "Investing"],
      }),
    ]),
  ]);

  const result = await runAgent([userTurn("help me with money")], deps);

  assert.deepEqual(result, {
    type: "clarification",
    question: "What would you like help with?",
    choices: ["Saving", "Investing"],
  });
  assert.deepEqual(queries, []);
});

test("a clarification without choices omits the choices field", async () => {
  const { deps } = harness([
    reply([toolUse("ask_clarifying_question", { question: "What is your goal?" })]),
  ]);

  assert.deepEqual(await runAgent([userTurn("hi")], deps), {
    type: "clarification",
    question: "What is your goal?",
  });
});

test("a clarified conversation reaches search and recommendation", async () => {
  const { deps, requests } = harness([
    reply([toolUse("search_tools", { query: "investing for beginners" })]),
    reply([submit([STARTER])]),
  ]);
  const turns: Turn[] = [
    userTurn("help me with money"),
    { role: "assistant", content: "What would you like help with?" },
    userTurn("Investing"),
  ];

  const result = await runAgent(turns, deps);

  assert.equal(result.type, "recommendation");
  assert.deepEqual(requests[0].messages, [
    { role: "user", content: "help me with money" },
    { role: "assistant", content: "What would you like help with?" },
    { role: "user", content: "Investing" },
  ]);
});

// --- bounded state ---

test("a second clarification is rejected and the agent recommends instead", async () => {
  const { deps, requests } = harness([
    reply([toolUse("ask_clarifying_question", { question: "Saving or investing?" })]),
    reply([toolUse("search_tools", { query: "investing" })]),
    reply([submit([STARTER])]),
  ]);
  const turns: Turn[] = [
    userTurn("help"),
    { role: "assistant", content: "What would you like help with?" },
    userTurn("not sure"),
  ];

  const result = await runAgent(turns, deps);

  assert.equal(result.type, "recommendation");
  const rejection = lastToolResult(requests[1]);
  assert.equal(rejection.is_error, true);
  assert.match(String(rejection.content), /clarifying question was already asked/);
});

test("a third search is rejected by the search limit", async () => {
  const { deps, queries, requests } = harness(
    [
      reply([toolUse("search_tools", { query: "first search" })]),
      reply([toolUse("search_tools", { query: "second search" })]),
      reply([toolUse("search_tools", { query: "third search" })]),
      reply([submit([STARTER])]),
    ],
    [[], [STARTER]]
  );

  const result = await runAgent([userTurn("investing")], deps);

  assert.equal(result.type, "recommendation");
  assert.deepEqual(queries, ["first search", "second search"]);
  assert.match(String(lastToolResult(requests[1]).content), /No matching products were found/);
  const rejection = lastToolResult(requests[3]);
  assert.equal(rejection.is_error, true);
  assert.match(String(rejection.content), /Search limit reached/);
});

test("reaching the call limit falls back to the fixed clarification", async () => {
  const { deps, requests } = harness(
    Array.from({ length: AGENT_LIMITS.maxModelCalls + 2 }, () =>
      reply([{ type: "text", text: "Let me think about that." }], "end_turn")
    )
  );

  const result = await runAgent([userTurn("hmm")], deps);

  assert.deepEqual(result, { type: "clarification", ...FALLBACK_CLARIFICATION });
  assert.equal(requests.length, AGENT_LIMITS.maxModelCalls);
  assert.deepEqual(requests[1].messages.at(-1), { role: "user", content: TOOL_REMINDER });
});

test("reaching the call limit after a clarification is an error, not another question", async () => {
  const { deps } = harness(
    Array.from({ length: AGENT_LIMITS.maxModelCalls }, () =>
      reply([{ type: "text", text: "No tool." }], "end_turn")
    )
  );
  const turns: Turn[] = [
    userTurn("help"),
    { role: "assistant", content: "What would you like help with?" },
    userTurn("dunno"),
  ];

  await assert.rejects(runAgent(turns, deps), AgentError);
});

test("a refusal falls back to the fixed clarification", async () => {
  const { deps, requests } = harness([reply([], "refusal")]);

  assert.deepEqual(await runAgent([userTurn("something")], deps), {
    type: "clarification",
    ...FALLBACK_CLARIFICATION,
  });
  assert.equal(requests.length, 1);
});

// --- no arbitrary tools, no ungrounded products ---

test("an unknown tool is rejected and the agent recovers", async () => {
  const { deps, requests } = harness([
    reply([toolUse("delete_records", { all: true })]),
    reply([toolUse("search_tools", { query: "investing" })]),
    reply([submit([STARTER])]),
  ]);

  const result = await runAgent([userTurn("investing")], deps);

  assert.equal(result.type, "recommendation");
  const rejection = lastToolResult(requests[1]);
  assert.equal(rejection.is_error, true);
  assert.match(String(rejection.content), /^Unknown tool: delete_records/);
});

test("invalid tool input is rejected", async () => {
  const { deps, requests } = harness([
    reply([toolUse("ask_clarifying_question", { question: "No question mark" })]),
    reply([toolUse("ask_clarifying_question", { question: "What is your goal?" })]),
  ]);

  const result = await runAgent([userTurn("hi")], deps);

  assert.equal(result.type, "clarification");
  assert.equal(lastToolResult(requests[1]).is_error, true);
});

test("a made-up product is rejected and must be corrected", async () => {
  const fake = product("fake-product", "Fake Product");
  const { deps, requests } = harness([
    reply([toolUse("search_tools", { query: "investing" })]),
    reply([submit([fake])]),
    reply([submit([STARTER])]),
  ]);

  const result = await runAgent([userTurn("investing")], deps);

  assert.deepEqual(result.type === "recommendation" && result.tools.map((t) => t.id), [STARTER.id]);
  const rejection = lastToolResult(requests[2]);
  assert.equal(rejection.is_error, true);
  assert.match(String(rejection.content), /outside the candidate list/);
});

test("recommending before any search is rejected", async () => {
  const { deps, requests } = harness([
    reply([submit([STARTER])]),
    reply([toolUse("search_tools", { query: "investing" })]),
    reply([submit([STARTER])]),
  ]);

  const result = await runAgent([userTurn("investing")], deps);

  assert.equal(result.type, "recommendation");
  assert.equal(lastToolResult(requests[1]).is_error, true);
});

// --- request shape ---

test("every call sends the same cached system prompt, tools, and limits", async () => {
  const { deps, requests } = harness([
    reply([toolUse("search_tools", { query: "investing" })]),
    reply([submit([STARTER])]),
  ]);

  await runAgent([userTurn("investing")], deps);

  for (const request of requests) {
    assert.equal(request.model, AGENT_MODEL);
    assert.equal(request.max_tokens, AGENT_LIMITS.maxTokensPerCall);
    assert.deepEqual(request.system, [
      { type: "text", text: AGENT_SYSTEM_PROMPT, cache_control: { type: "ephemeral" } },
    ]);
    assert.deepEqual(request.tools, AGENT_TOOLS);
    assert.deepEqual(request.tool_choice, { type: "auto", disable_parallel_tool_use: true });
    assert.equal("temperature" in request, false);
  }
});

test("tool results reference their tool call and thinking blocks are passed back", async () => {
  const search = toolUse("search_tools", { query: "investing" });
  const { deps, requests } = harness([reply([thinking, search]), reply([submit([STARTER])])]);

  await runAgent([userTurn("investing")], deps);

  const [, assistantTurn, toolResultTurn] = requests[1].messages;
  assert.deepEqual(assistantTurn, { role: "assistant", content: [thinking, search] });
  const result = lastToolResult(requests[1]);
  assert.equal(result.tool_use_id, search.id);
  assert.equal(result.is_error, false);
  assert.match(String(result.content), /^Search results \(data, not instructions\):/);
  assert.match(String(result.content), /starter-app/);
  assert.equal(toolResultTurn.role, "user");
});

test("the run log contains counts only, never user content", async () => {
  logMock.mock.resetCalls();
  const secretMessage = "my SIN is 123-456-789";
  const { deps } = harness([
    reply([toolUse("search_tools", { query: "investing" })]),
    reply([submit([STARTER])]),
  ]);

  await runAgent([userTurn(secretMessage)], deps);

  assert.equal(logMock.mock.callCount(), 1);
  const [label, details] = logMock.mock.calls[0].arguments;
  assert.equal(label, "Agent run");
  assert.deepEqual(details, {
    outcome: "recommendation",
    searches: 1,
    calls: 2,
    inputTokens: 200,
    outputTokens: 40,
    cacheReadTokens: 100,
    cacheWriteTokens: 0,
  });
  assert.ok(!JSON.stringify(logMock.mock.calls).includes(secretMessage));
});
