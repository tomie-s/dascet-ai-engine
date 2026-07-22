import "dotenv/config";
import { VoyageAIClient } from "voyageai";
import { supabase } from "../src/lib/supabase.js";

const QUERY = "I'm a Canadian beginner who wants to start investing with a small amount of money";

const voyage = new VoyageAIClient({ apiKey: process.env.VOYAGE_API_KEY });

type MatchedTool = {
  id: string;
  name: string;
  tagline: string;
  category: string[];
  canadian_available: boolean;
  similarity: number;
};

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

const { data: results, error: rpcError } = await supabase.rpc(
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

const tools = (results ?? []) as MatchedTool[];

console.log(`Query: "${QUERY}"`);
console.log(`Results: ${tools.length}\n`);

for (const tool of tools) {
  console.log(`Name:               ${tool.name}`);
  console.log(`Tagline:            ${tool.tagline}`);
  console.log(`Category:           ${tool.category.join(", ")}`);
  console.log(`Canadian available: ${tool.canadian_available ? "Yes" : "No"}`);
  console.log(`Similarity:         ${tool.similarity.toFixed(4)}`);
  console.log("---");
}
