import "dotenv/config";
import { VoyageAIClient } from "voyageai";
import { supabase } from "../src/lib/supabase.js";

const voyage = new VoyageAIClient({ apiKey: process.env.VOYAGE_API_KEY });

type Tool = {
  id: string;
  name: string;
  tagline: string;
  description: string | null;
  category: string[];
  target_situations: string[];
  key_features: string[];
  experience_level: string | null;
  pricing_model: string | null;
  pricing_plain: string | null;
  canadian_available: boolean;
};

function buildToolText(tool: Tool): string {
  const lines: string[] = [
    `Name: ${tool.name}`,
    `Tagline: ${tool.tagline}`,
  ];

  if (tool.description) lines.push(`Description: ${tool.description}`);

  if (Array.isArray(tool.category) && tool.category.length > 0) {
    lines.push(`Category: ${tool.category.join(", ")}`);
  }

  if (Array.isArray(tool.target_situations) && tool.target_situations.length > 0) {
    lines.push(`Best for: ${tool.target_situations.join(", ")}`);
  }

  if (Array.isArray(tool.key_features) && tool.key_features.length > 0) {
    lines.push(`Key features: ${tool.key_features.join(", ")}`);
  }

  if (tool.experience_level) {
    lines.push(`Experience level: ${tool.experience_level}`);
  }

  if (tool.pricing_plain) {
    lines.push(`Pricing: ${tool.pricing_plain}`);
  } else if (tool.pricing_model) {
    lines.push(`Pricing model: ${tool.pricing_model}`);
  }

  lines.push(`Available in Canada: ${tool.canadian_available ? "Yes" : "No"}`);

  return lines.join("\n");
}

const { data: tools, error: fetchError } = await supabase
  .from("financial_tools")
  .select(
    "id, name, tagline, description, category, target_situations, key_features, experience_level, pricing_model, pricing_plain, canadian_available"
  )
  .eq("status", "approved")
  .is("embedding", null);

if (fetchError) {
  console.error("Failed to fetch tools:", fetchError.message);
  process.exit(1);
}

if (!tools || tools.length === 0) {
  console.log("No approved tools with missing embeddings found.");
  process.exit(0);
}

console.log(`Found ${tools.length} tools to embed.\n`);

const BATCH_SIZE = 10;
let totalEmbedded = 0;
let totalFailed = 0;

for (let i = 0; i < tools.length; i += BATCH_SIZE) {
  const batch = tools.slice(i, i + BATCH_SIZE) as Tool[];
  const batchNumber = Math.floor(i / BATCH_SIZE) + 1;
  const fromIndex = i + 1;
  const toIndex = Math.min(i + BATCH_SIZE, tools.length);

  const texts = batch.map(buildToolText);

  let embeddings: number[][];

  try {
    const response = await voyage.embed({
      model: "voyage-3-lite",
      input: texts,
      inputType: "document",
    });

    embeddings = response.data!.map((d) => d.embedding!);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`Batch ${batchNumber} embedding failed: ${message}`);
    totalFailed += batch.length;
    continue;
  }

  for (let j = 0; j < batch.length; j++) {
    const tool = batch[j];
    const embedding = embeddings[j];

    const { error: updateError } = await supabase
      .from("financial_tools")
      .update({ embedding })
      .eq("id", tool.id);

    if (updateError) {
      console.error(`  Failed to update "${tool.name}": ${updateError.message}`);
      totalFailed++;
    } else {
      totalEmbedded++;
    }
  }

  console.log(`Embedded batch ${batchNumber} — tools ${fromIndex} to ${toIndex}`);

  if (i + BATCH_SIZE < tools.length) {
    await new Promise((resolve) => setTimeout(resolve, 21000));
  }
}

console.log(`\n--- Summary ---`);
console.log(`Total embedded: ${totalEmbedded}`);
if (totalFailed > 0) {
  console.log(`Failed / skipped: ${totalFailed}`);
} else {
  console.log(`Failed / skipped: 0`);
}
