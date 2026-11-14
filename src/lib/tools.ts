import type Anthropic from "@anthropic-ai/sdk";
import { z } from "zod";
import { recommendationSchema } from "./recommendation-response.js";

/** Cheapest current model. Phase 6 evaluation decides whether it is good enough. */
export const AGENT_MODEL = "claude-haiku-5-5";

/**
 * Hard per-request bounds. They cap the worst-case cost of a single request
 * and keep client-held conversation state small.
 */
export const AGENT_LIMITS = {
  maxModelCalls: 4,
  maxSearches: 2,
  maxClarifications: 1,
  maxTurns: 3,
  maxTokensPerCall: 4_096,
} as const;

export const searchToolsInputSchema = z.object({
  query: z.string().trim().min(3).max(300),
});

export const askClarifyingQuestionInputSchema = z.object({
  question: z.string().trim().min(1).max(200).endsWith("?"),
  choices: z.array(z.string().trim().min(1).max(60)).min(2).max(5).optional(),
});

export const submitRecommendationInputSchema = recommendationSchema;

const toolInputSchemas = {
  search_tools: searchToolsInputSchema,
  ask_clarifying_question: askClarifyingQuestionInputSchema,
  submit_recommendation: submitRecommendationInputSchema,
} as const;

export type AgentToolName = keyof typeof toolInputSchemas;

export type ToolCall =
  | { name: "search_tools"; input: z.infer<typeof searchToolsInputSchema> }
  | { name: "ask_clarifying_question"; input: z.infer<typeof askClarifyingQuestionInputSchema> }
  | { name: "submit_recommendation"; input: z.infer<typeof submitRecommendationInputSchema> };

export class ToolCallError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ToolCallError";
  }
}

/**
 * The only gate between a model tool call and our code: unknown names and
 * invalid inputs are rejected before anything runs.
 */
export function parseToolCall(name: string, input: unknown): ToolCall {
  if (!Object.hasOwn(toolInputSchemas, name)) {
    throw new ToolCallError(
      `Unknown tool: ${name}. Available tools: ${Object.keys(toolInputSchemas).join(", ")}.`
    );
  }

  const toolName = name as AgentToolName;
  const parsed = toolInputSchemas[toolName].safeParse(input);

  if (!parsed.success) {
    const issues = parsed.error.issues
      .map((issue) => `${issue.path.join(".") || "input"}: ${issue.message}`)
      .join("; ");
    throw new ToolCallError(`Invalid input for ${toolName}: ${issues}`);
  }

  return { name: toolName, input: parsed.data } as ToolCall;
}

/** Sent to the API in this fixed order so the request prefix stays cacheable. */
export const AGENT_TOOLS: Anthropic.Tool[] = [
  {
    name: "search_tools",
    description:
      "Search Dascet's catalogue of Canadian financial products by meaning. " +
      "Returns up to five candidate products with their IDs, names, and details. " +
      "Call this before submit_recommendation.",
    input_schema: {
      type: "object",
      properties: {
        query: {
          type: "string",
          minLength: 3,
          maxLength: 300,
          description: "The user's financial need described in plain words.",
        },
      },
      required: ["query"],
      additionalProperties: false,
    },
  },
  {
    name: "ask_clarifying_question",
    description:
      "Ask the user one short question when no financial goal or product type can be " +
      "identified from their messages. Ends the run and waits for the user's answer.",
    input_schema: {
      type: "object",
      properties: {
        question: {
          type: "string",
          minLength: 1,
          maxLength: 200,
          description: "One question about one thing, ending with a question mark.",
        },
        choices: {
          type: "array",
          items: { type: "string", minLength: 1, maxLength: 60 },
          minItems: 2,
          maxItems: 5,
          description: "Optional short answer choices when the answer is one of a few categories.",
        },
      },
      required: ["question"],
      additionalProperties: false,
    },
  },
  {
    name: "submit_recommendation",
    description:
      "Return the final recommendation using only products returned by search_tools in " +
      "this conversation. Ends the run.",
    input_schema: {
      type: "object",
      properties: {
        tools: {
          type: "array",
          minItems: 1,
          items: {
            type: "object",
            properties: {
              id: { type: "string", description: "Product ID copied exactly from search results." },
              name: { type: "string", description: "Product name copied exactly from search results." },
              why: {
                type: "string",
                description:
                  "One or two sentences explaining what this product does and why it may be relevant.",
              },
            },
            required: ["id", "name", "why"],
            additionalProperties: false,
          },
        },
        explanation: {
          type: "string",
          description:
            "Two or three sentences acknowledging the user's situation and framing these " +
            "products as options to explore, not a ranked list or financial advice.",
        },
      },
      required: ["tools", "explanation"],
      additionalProperties: false,
    },
  },
];
