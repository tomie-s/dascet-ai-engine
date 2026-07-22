import "dotenv/config";
import { VoyageAIClient } from "voyageai";
import { supabase } from "../src/lib/supabase.js";

const voyage = new VoyageAIClient({ apiKey: process.env.VOYAGE_API_KEY });

const { data, error } = await supabase
  .from("financial_tools")
  .select(
    "name, tagline, description, category, target_situations, key_features, experience_level, pricing_model, pricing_plain, canadian_available"
  )
  .eq("status", "approved")
  .limit(1)
  .single();

if (error) {
  console.error("Supabase fetch failed:", error.message);
  process.exit(1);
}

const lines: string[] = [
  `Name: ${data.name}`,
  `Tagline: ${data.tagline}`,
];

if (data.description) lines.push(`Description: ${data.description}`);

if (Array.isArray(data.category) && data.category.length > 0) {
  lines.push(`Category: ${data.category.join(", ")}`);
}

if (Array.isArray(data.target_situations) && data.target_situations.length > 0) {
  lines.push(`Best for: ${data.target_situations.join(", ")}`);
}

if (Array.isArray(data.key_features) && data.key_features.length > 0) {
  lines.push(`Key features: ${data.key_features.join(", ")}`);
}

if (data.experience_level) {
  lines.push(`Experience level: ${data.experience_level}`);
}

if (data.pricing_plain) {
  lines.push(`Pricing: ${data.pricing_plain}`);
} else if (data.pricing_model) {
  lines.push(`Pricing model: ${data.pricing_model}`);
}

lines.push(`Available in Canada: ${data.canadian_available ? "Yes" : "No"}`);

const text = lines.join("\n");

const embeddingResponse = await voyage.embed({
  model: "voyage-3-lite",
  input: text,
  inputType: "document",
}).catch((err: unknown) => {
  console.error("Voyage AI embedding failed:", err instanceof Error ? err.message : err);
  process.exit(1);
});

const vector = embeddingResponse.data![0].embedding!;

console.log("Tool name:", data.name);
console.log("\n--- Text sent for embedding ---\n");
console.log(text);
console.log("\n--- Embedding results ---");
console.log("Vector length:", vector.length);
console.log(
  "First 10 values:",
  vector.slice(0, 10).map((v) => v.toFixed(6)).join(", ")
);
console.log("\nSuccess: embedding generated for", data.name);
