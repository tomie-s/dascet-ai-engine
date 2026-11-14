import assert from "node:assert/strict";
import type Anthropic from "@anthropic-ai/sdk";
import type { AgentDeps, Turn } from "../src/lib/agent.js";
import type { PromptTool } from "../src/lib/prompt.js";
import { AGENT_MODEL } from "../src/lib/tools.js";

/** Shared fakes for the agent and integration tests. No network or paid calls. */

export const product = (id: string, name: string): PromptTool => ({
  id,
  name,
  tagline: `${name} tagline`,
  description: null,
  target_situations: ["investing"],
  key_features: null,
  experience_level: "Beginner",
  pricing_plain: null,
  canadian_available: true,
});

export const STARTER = product("starter-app", "Starter Investing App");
export const ROBO = product("robo-advisor", "Robo Advisor");

let toolUseCounter = 0;

export function toolUse(name: string, input: unknown) {
  toolUseCounter += 1;
  return { type: "tool_use", id: `toolu_${toolUseCounter}`, name, input };
}

export function reply(
  content: unknown[],
  stopReason: Anthropic.StopReason = "tool_use"
): Anthropic.Message {
  return {
    id: "msg_test",
    type: "message",
    role: "assistant",
    model: AGENT_MODEL,
    content,
    stop_reason: stopReason,
    stop_sequence: null,
    usage: {
      input_tokens: 100,
      output_tokens: 20,
      cache_read_input_tokens: 50,
      cache_creation_input_tokens: 0,
    },
  } as unknown as Anthropic.Message;
}

export const thinking = { type: "thinking", thinking: "", signature: "sig" };

export const submit = (tools: PromptTool[]) =>
  toolUse("submit_recommendation", {
    tools: tools.map((tool) => ({ id: tool.id, name: tool.name, why: "It may be relevant." })),
    explanation: "Options to explore.",
  });

export const userTurn = (content: string): Turn => ({ role: "user", content });

/**
 * A scripted fake model plus a fake catalogue search. Each model call takes
 * the next scripted reply; each search takes the next result set.
 */
export function harness(
  script: Anthropic.Message[],
  searchResults: PromptTool[][] = [[STARTER, ROBO]]
): {
  deps: AgentDeps;
  requests: Anthropic.MessageCreateParamsNonStreaming[];
  queries: string[];
} {
  const requests: Anthropic.MessageCreateParamsNonStreaming[] = [];
  const queries: string[] = [];
  return {
    requests,
    queries,
    deps: {
      createMessage: async (params) => {
        requests.push(structuredClone(params));
        const next = script.shift();
        if (!next) throw new Error("Script exhausted");
        return next;
      },
      searchTools: async (query) => {
        queries.push(query);
        return searchResults.shift() ?? [];
      },
    },
  };
}

export const lastToolResult = (request: Anthropic.MessageCreateParamsNonStreaming) => {
  const last = request.messages.at(-1);
  assert.ok(last && Array.isArray(last.content));
  const block = last.content[0];
  assert.equal(block.type, "tool_result");
  return block as Anthropic.ToolResultBlockParam;
};
