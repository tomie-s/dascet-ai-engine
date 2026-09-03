import Anthropic from "@anthropic-ai/sdk";
import { VoyageAIClient } from "voyageai";
import { buildRecommendationPrompt, RECOMMENDATION_SYSTEM_PROMPT } from "./prompt.js";
import { parseModelResponse } from "./recommendation-response.js";
import { supabase } from "./supabase.js";

export type { Recommendation } from "./recommendation-response.js";

const MATCH_THRESHOLD = 0.45;
const MATCH_COUNT = 5;

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

export class NoMatchesError extends Error {
  constructor() {
    super("No matching products were found");
    this.name = "NoMatchesError";
  }
}

export async function recommend(
  message: string
): Promise<import("./recommendation-response.js").Recommendation> {
  const voyageApiKey = process.env.VOYAGE_API_KEY;
  const anthropicApiKey = process.env.ANTHROPIC_API_KEY;

  if (!voyageApiKey || !anthropicApiKey) {
    throw new Error("The AI provider API keys are not configured");
  }

  const voyage = new VoyageAIClient({ apiKey: voyageApiKey });
  const anthropic = new Anthropic({ apiKey: anthropicApiKey });
  const retrievalQuery = `Canadian financial product discovery request: ${message}`;
  const embeddingResponse = await voyage.embed({
    model: "voyage-3-lite",
    input: [retrievalQuery],
    inputType: "query",
  });
  const embedding = embeddingResponse.data?.[0]?.embedding;

  if (!embedding) {
    throw new Error("Voyage AI did not return an embedding");
  }

  const { data: matches, error: matchError } = await supabase.rpc(
    "match_financial_tools",
    {
      query_embedding: embedding,
      match_threshold: MATCH_THRESHOLD,
      match_count: MATCH_COUNT,
    }
  );

  if (matchError) throw new Error(`Vector search failed: ${matchError.message}`);

  const matchedIds: string[] = (matches ?? []).map(
    (row: { id: string }) => row.id
  );
  if (matchedIds.length === 0) throw new NoMatchesError();

  const { data, error: selectError } = await supabase
    .from("financial_tools")
    .select(
      "id, name, tagline, description, target_situations, key_features, experience_level, pricing_plain, canadian_available"
    )
    .in("id", matchedIds);

  if (selectError) {
    throw new Error(`Product lookup failed: ${selectError.message}`);
  }

  const fetchedTools = (data ?? []) as FinancialTool[];
  const tools = matchedIds
    .map((id) => fetchedTools.find((tool) => tool.id === id))
    .filter((tool): tool is FinancialTool => tool !== undefined);

  if (tools.length === 0) throw new NoMatchesError();

  const canadianTools = tools.filter((tool) => tool.canadian_available);
  const promptTools = canadianTools.length > 0 ? canadianTools : tools;

  const response = await anthropic.messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 1024,
    temperature: 0,
    system: RECOMMENDATION_SYSTEM_PROMPT,
    messages: [
      { role: "user", content: buildRecommendationPrompt(message, promptTools) },
    ],
  });
  const rawText = response.content.find((block) => block.type === "text")?.text;

  if (!rawText) throw new Error("Claude did not return a text response");

  return parseModelResponse(rawText, promptTools);
}
