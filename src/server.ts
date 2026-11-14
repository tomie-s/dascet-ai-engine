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

const server = serve({ fetch: app.fetch, port: config.port }, (info) => {
  console.log(`Dascet AI Engine listening on port ${info.port}`);
});

const SHUTDOWN_TIMEOUT_MS = 10_000;

// Railway sends SIGTERM on every redeploy: stop accepting connections and let
// in-flight requests finish, but never hang past the timeout.
function shutdown(signal: NodeJS.Signals) {
  console.log(`${signal} received, closing server`);
  server.close((error) => process.exit(error ? 1 : 0));
  setTimeout(() => process.exit(1), SHUTDOWN_TIMEOUT_MS).unref();
}

process.once("SIGTERM", shutdown);
process.once("SIGINT", shutdown);
