import "dotenv/config";
import { serve } from "@hono/node-server";
import { app } from "./app.js";

const configuredPort = Number.parseInt(process.env.PORT ?? "3000", 10);
const port = Number.isNaN(configuredPort) ? 3000 : configuredPort;

serve({ fetch: app.fetch, port }, (info) => {
  console.log(`Dascet AI Engine listening on http://localhost:${info.port}`);
});
