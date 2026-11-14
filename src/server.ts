import "dotenv/config";
import { serve } from "@hono/node-server";
import { type Config, ConfigError, loadConfig } from "./config.js";

function loadConfigOrExit(): Config {
  try {
    return loadConfig();
  } catch (error) {
    if (error instanceof ConfigError) {
      console.error(error.message);
      process.exit(1);
    }
    throw error;
  }
}

const config = loadConfigOrExit();

// Imported after validation so a misconfigured server fails with the full list
// of problems above rather than the first module-level throw.
const { app } = await import("./app.js");

serve({ fetch: app.fetch, port: config.port }, (info) => {
  console.log(`Dascet AI Engine listening on http://localhost:${info.port}`);
});
