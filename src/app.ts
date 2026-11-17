import { type ErrorHandler, Hono } from "hono";
import { createRateLimiter } from "./lib/rate-limit.js";
import { recommendRoute } from "./routes/recommend.js";

export const UNEXPECTED_ERROR_MESSAGE = "Something went wrong.";

/** Log only the name and message: errors can carry request details. */
export const handleUnexpectedError: ErrorHandler = (error, context) => {
  console.error("Unhandled request error", { name: error.name, message: error.message });
  return context.json({ error: UNEXPECTED_ERROR_MESSAGE }, 500);
};

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
// Production only, so local eval runs (36 requests back to back) are not limited.
if (process.env.NODE_ENV === "production") app.use("/recommend", createRateLimiter());
app.route("/recommend", recommendRoute);
app.notFound((context) => context.json({ error: "Not found." }, 404));
app.onError(handleUnexpectedError);

export { app };
