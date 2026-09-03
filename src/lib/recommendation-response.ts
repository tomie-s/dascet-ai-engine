import { z } from "zod";

const recommendationSchema = z.object({
  tools: z
    .array(
      z.object({
        id: z.string().min(1),
        name: z.string().min(1),
        why: z.string().min(1),
      })
    )
    .min(1),
  explanation: z.string().min(1),
});

type RecommendationCandidate = {
  id: string;
  name: string;
};

export type Recommendation = z.infer<typeof recommendationSchema>;

export function parseModelResponse(
  rawText: string,
  candidates: RecommendationCandidate[]
): Recommendation {
  const cleaned = rawText
    .replace(/^```json\s*/i, "")
    .replace(/```\s*$/i, "")
    .trim();
  const recommendation = recommendationSchema.parse(JSON.parse(cleaned));
  const candidatesById = new Map(candidates.map((tool) => [tool.id, tool]));

  for (const result of recommendation.tools) {
    const candidate = candidatesById.get(result.id);
    if (!candidate || candidate.name !== result.name) {
      throw new Error("The model returned a product outside the candidate list");
    }
  }

  const uniqueIds = new Set(recommendation.tools.map((tool) => tool.id));
  if (uniqueIds.size !== recommendation.tools.length) {
    throw new Error("The model returned the same product more than once");
  }

  return recommendation;
}
