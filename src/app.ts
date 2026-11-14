import { Hono } from "hono";
import { recommendRoute } from "./routes/recommend.js";

const app = new Hono();

app.get("/", (context) =>
  context.json({
    name: "Dascet AI Engine",
    status: "running",
    endpoints: {
      health: "GET /health",
      recommend: "POST /recommend",
    },
  })
);
app.get("/health", (context) => context.json({ status: "ok" }));
app.route("/recommend", recommendRoute);
app.notFound((context) => context.json({ error: "Not found." }, 404));

export { app };
