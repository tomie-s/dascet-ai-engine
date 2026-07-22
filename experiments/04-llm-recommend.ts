import "dotenv/config";
import { VoyageAIClient } from "voyageai";
import Anthropic from "@anthropic-ai/sdk";
import { supabase } from "../src/lib/supabase.js";

const QUERY = "I'm a Canadian beginner who wants to start investing with a small amount of money";

const voyage = new VoyageAIClient({ apiKey: process.env.VOYAGE_API_KEY });

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

// Step 1: Embed the query
let embedding: number[];

try {
  const response = await voyage.embed({
    model: "voyage-3-lite",
    input: [QUERY],
    inputType: "query",
  });
  embedding = response.data![0].embedding!;
} catch (err) {
  const message = err instanceof Error ? err.message : String(err);
  console.error("Voyage AI embedding failed:", message);
  process.exit(1);
}

// Step 2: Get top 5 vector search results
const { data: rpcResults, error: rpcError } = await supabase.rpc(
  "match_financial_tools",
  {
    query_embedding: embedding,
    match_threshold: 0.45,
    match_count: 5,
  }
);

if (rpcError) {
  console.error("Supabase RPC failed:", rpcError.message);
  process.exit(1);
}

// Step 3: Extract IDs
const matchedIds: string[] = (rpcResults ?? []).map(
  (row: { id: string; similarity: number }) => row.id
);

if (matchedIds.length === 0) {
  console.error("No results returned from vector search.");
  process.exit(1);
}

// Step 4: Fetch full tool data for those IDs
type FinancialTool = {
  id: string;
  name: string;
  tagline: string;
  description: string | null;
  target_situations: string[] | null;
  key_features: string[] | null;
  experience_level: string | null;
  pricing_plain: string | null;
  canadian_available: boolean;
};

const { data: tools, error: selectError } = await supabase
  .from("financial_tools")
  .select(
    "id, name, tagline, description, target_situations, key_features, experience_level, pricing_plain, canadian_available"
  )
  .in("id", matchedIds);

if (selectError) {
  console.error("Supabase select failed:", selectError.message);
  process.exit(1);
}

if (!tools || tools.length === 0) {
  console.error("No tool data returned from Supabase select.");
  process.exit(1);
}

const orderedTools = matchedIds
  .map(id => (tools as FinancialTool[]).find(t => t.id === id))
  .filter((t): t is FinancialTool => t !== undefined);

// Step 5: Build system prompt and user message
const systemPrompt = `You are a financial literacy assistant for Dascet, a Canadian fintech app.
Your job is to help users understand which financial tools might be relevant
to their situation.

Rules you must always follow:
- Never tell a user what they should do with their money
- Never recommend one tool over another — describe what each tool does and
  let the user decide
- Use plain, warm, jargon-free language
- Only reference tools from the list provided — do not suggest tools from
  outside this list
- If a tool is not available in Canada, still include it but clearly note
  that it is not currently available in Canada
- Do not wrap the JSON in markdown code fences or backticks

Respond with valid JSON only. No prose outside the JSON. Use this exact shape:
{
  "tools": [
    {
      "name": "Tool Name",
      "why": "1–2 sentences explaining what this tool does and why it's relevant to what the user described"
    }
  ],
  "explanation": "2–3 sentences that acknowledge the user's situation and frame the tools as options to explore — not a ranked list, not advice"
}`;

const toolBlocks = orderedTools.map((tool, index) => {
  const lines: string[] = [
    `Tool ${index + 1}:`,
    `Name: ${tool.name}`,
    `Tagline: ${tool.tagline}`,
  ];

  if (tool.description) lines.push(`Description: ${tool.description}`);

  if (Array.isArray(tool.target_situations) && tool.target_situations.length > 0) {
    lines.push(`Best for: ${tool.target_situations.join(", ")}`);
  }

  if (Array.isArray(tool.key_features) && tool.key_features.length > 0) {
    lines.push(`Key features: ${tool.key_features.join(", ")}`);
  }

  if (tool.experience_level) lines.push(`Experience level: ${tool.experience_level}`);
  if (tool.pricing_plain) lines.push(`Pricing: ${tool.pricing_plain}`);

  lines.push(`Available in Canada: ${tool.canadian_available ? "Yes" : "No"}`);

  return lines.join("\n");
});

const userMessage = `The user said: "${QUERY}"

Here are the relevant tools from the Dascet database:

${toolBlocks.join("\n\n")}

Respond using only these tools. Do not reference any tools not listed above.`;

// Step 6: Call Claude
let claudeResponse;

try {
  claudeResponse = await anthropic.messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 1024,
    system: systemPrompt,
    messages: [{ role: "user", content: userMessage }],
  });
} catch (err) {
  const message = err instanceof Error ? err.message : String(err);
  console.error("Anthropic API call failed:", message);
  process.exit(1);
}

// Step 7: Parse the JSON response
const rawText = claudeResponse.content[0].type === "text"
  ? claudeResponse.content[0].text
  : "";

let parsed;

try {
  const cleaned = rawText.replace(/^```json\s*/i, "").replace(/```\s*$/i, "").trim();
  parsed = JSON.parse(cleaned);
} catch {
  console.error("Failed to parse Claude's response as JSON:");
  console.error(rawText);
  process.exit(1);
}

// Step 8: Print the result
console.log(JSON.stringify(parsed, null, 2));
