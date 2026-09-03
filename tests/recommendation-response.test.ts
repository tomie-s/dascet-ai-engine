import assert from "node:assert/strict";
import test from "node:test";
import { parseModelResponse } from "../src/lib/recommendation-response.js";

const candidates = [
  { id: "one", name: "Product One" },
  { id: "two", name: "Product Two" },
];

const validResponse = {
  tools: [{ id: "one", name: "Product One", why: "Relevant context." }],
  explanation: "Options to explore.",
};

test("accepts a valid candidate-bound response", () => {
  assert.deepEqual(
    parseModelResponse(JSON.stringify(validResponse), candidates),
    validResponse
  );
});

test("tolerates an unnecessary JSON markdown fence", () => {
  const raw = `\`\`\`json\n${JSON.stringify(validResponse)}\n\`\`\``;
  assert.deepEqual(parseModelResponse(raw, candidates), validResponse);
});

test("rejects hallucinated products and changed names", () => {
  const outsider = {
    ...validResponse,
    tools: [{ id: "three", name: "Product Three", why: "Not retrieved." }],
  };
  const renamed = {
    ...validResponse,
    tools: [{ id: "one", name: "Wrong Name", why: "Changed name." }],
  };

  assert.throws(
    () => parseModelResponse(JSON.stringify(outsider), candidates),
    /outside the candidate list/
  );
  assert.throws(
    () => parseModelResponse(JSON.stringify(renamed), candidates),
    /outside the candidate list/
  );
});

test("rejects duplicate products", () => {
  const duplicate = {
    ...validResponse,
    tools: [validResponse.tools[0], validResponse.tools[0]],
  };

  assert.throws(
    () => parseModelResponse(JSON.stringify(duplicate), candidates),
    /same product more than once/
  );
});

test("rejects malformed model output", () => {
  assert.throws(() => parseModelResponse("not JSON", candidates));
  assert.throws(() =>
    parseModelResponse(JSON.stringify({ tools: [], explanation: "" }), candidates)
  );
});
