import "dotenv/config";
import assert from "node:assert/strict";
import { supabase } from "../src/lib/supabase.js";

const EXPECTED_TOTAL = 210;
const EXPECTED_APPROVED = 205;
const EXPECTED_EMBEDDED = 205;
const EMBEDDING_DIMENSION = 512;
const MATCH_COUNT = 5;
const MATCH_THRESHOLD = 0.45;

type ToolRow = {
  id: string;
  name: string;
  tagline: string;
  status: string;
  embedding: number[] | string | null;
};

type MatchRow = {
  id: string;
  similarity: number;
};

function parseEmbedding(value: ToolRow["embedding"]): number[] | null {
  if (value === null) return null;
  if (Array.isArray(value)) return value;

  const parsed: unknown = JSON.parse(value);
  assert(Array.isArray(parsed), "Stored embedding must decode to an array");
  assert(
    parsed.every((item) => typeof item === "number"),
    "Stored embedding must contain only numbers"
  );

  return parsed as number[];
}

function pass(message: string): void {
  console.log(`✓ ${message}`);
}

async function run(): Promise<void> {
  const { data, error } = await supabase
    .from("financial_tools")
    .select("id, name, tagline, status, embedding")
    .order("id");

  assert.equal(error, null, `Database query failed: ${error?.message}`);

  const tools = (data ?? []) as ToolRow[];
  assert.equal(tools.length, EXPECTED_TOTAL);
  pass(`${EXPECTED_TOTAL} catalogue rows found`);

  const ids = new Set(tools.map((tool) => tool.id));
  assert.equal(ids.size, tools.length, "Duplicate tool IDs found");
  pass("tool IDs are unique");

  const missingRequiredFields = tools.filter(
    (tool) => !tool.id || !tool.name.trim() || !tool.tagline.trim() || !tool.status
  );
  assert.equal(
    missingRequiredFields.length,
    0,
    "Tools with missing required fields found"
  );
  pass("required catalogue fields are populated");

  const approved = tools.filter((tool) => tool.status === "approved");
  assert.equal(approved.length, EXPECTED_APPROVED);
  pass(`${EXPECTED_APPROVED} approved tools found`);

  const approvedEmbeddings = approved.map((tool) => ({
    tool,
    embedding: parseEmbedding(tool.embedding),
  }));

  const embeddedCount = approvedEmbeddings.filter(
    ({ embedding }) => embedding !== null
  ).length;
  assert.equal(embeddedCount, EXPECTED_EMBEDDED);
  pass(`${EXPECTED_EMBEDDED} approved tools have embeddings`);

  for (const { tool, embedding } of approvedEmbeddings) {
    assert(embedding, `Approved tool ${tool.id} is missing an embedding`);
    assert.equal(
      embedding.length,
      EMBEDDING_DIMENSION,
      `Tool ${tool.id} has an unexpected embedding dimension`
    );
  }
  pass(`all approved embeddings have ${EMBEDDING_DIMENSION} dimensions`);

  const sample = approvedEmbeddings[0];
  assert(sample?.embedding, "No approved embedding available for search test");

  const { data: matchData, error: matchError } = await supabase.rpc(
    "match_financial_tools",
    {
      query_embedding: sample.embedding,
      match_threshold: MATCH_THRESHOLD,
      match_count: MATCH_COUNT,
    }
  );

  assert.equal(
    matchError,
    null,
    `Vector search failed: ${matchError?.message}`
  );

  const matches = (matchData ?? []) as MatchRow[];
  assert.equal(matches.length, MATCH_COUNT);
  pass(`vector search respects the ${MATCH_COUNT}-result limit`);

  assert.equal(matches[0]?.id, sample.tool.id);
  assert(
    Math.abs((matches[0]?.similarity ?? 0) - 1) < 1e-6,
    "A stored embedding did not retrieve itself with similarity 1"
  );
  pass("a stored embedding retrieves its own tool first at similarity 1");

  for (let index = 0; index < matches.length; index++) {
    assert(
      matches[index].similarity >= MATCH_THRESHOLD,
      "A result fell below the requested similarity threshold"
    );

    if (index > 0) {
      assert(
        matches[index - 1].similarity >= matches[index].similarity,
        "Vector-search results are not ordered by descending similarity"
      );
    }
  }
  pass("search results are ordered and meet the similarity threshold");

  console.log("\nPhase 1–2 regression suite passed.");
}

run().catch((error: unknown) => {
  console.error("\nPhase 1–2 regression suite failed.");
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});

