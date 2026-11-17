import { z } from "zod";

const envSchema = z.object({
  SUPABASE_URL: z.string().trim().url(),
  SUPABASE_SERVICE_ROLE_KEY: z.string().trim().min(1),
  VOYAGE_API_KEY: z.string().trim().min(1),
  ANTHROPIC_API_KEY: z.string().trim().min(1),
  PORT: z.coerce.number().int().min(1).max(65_535).default(3000),
});

export type Config = {
  supabaseUrl: string;
  supabaseServiceRoleKey: string;
  voyageApiKey: string;
  anthropicApiKey: string;
  port: number;
};

export class ConfigError extends Error {
  constructor(readonly issues: string[]) {
    super(`Invalid configuration:\n${issues.map((issue) => `  - ${issue}`).join("\n")}`);
    this.name = "ConfigError";
  }
}

/**
 * Validates the server's environment, reporting every problem at once.
 * Messages name variables only — secret values are never included.
 */
export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const parsed = envSchema.safeParse(env);
  const issues = parsed.success
    ? []
    : parsed.error.issues.map((issue) => {
        const name = issue.path.join(".");
        const value = env[name];
        return value === undefined || value.trim() === ""
          ? `${name} is required`
          : `${name} is invalid (${issue.message})`;
      });

  // Usage counts are for local evaluation only and must never reach production clients.
  if (env.NODE_ENV === "production" && env.EVAL_INCLUDE_USAGE?.trim()) {
    issues.push("EVAL_INCLUDE_USAGE must not be set in production");
  }

  if (!parsed.success || issues.length > 0) throw new ConfigError(issues);

  const values = parsed.data;
  return {
    supabaseUrl: values.SUPABASE_URL,
    supabaseServiceRoleKey: values.SUPABASE_SERVICE_ROLE_KEY,
    voyageApiKey: values.VOYAGE_API_KEY,
    anthropicApiKey: values.ANTHROPIC_API_KEY,
    port: values.PORT,
  };
}
