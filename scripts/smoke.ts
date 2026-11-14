/**
 * Smoke test for a running Dascet AI Engine (local, Docker, or Railway).
 *
 *   npm run smoke -- <base-url>              # all checks, including one paid agent run
 *   npm run smoke -- <base-url> --skip-paid  # free checks only
 *
 * Prints only statuses and response types — never response bodies or secrets.
 * Exits 1 if any check fails.
 */

const FREE_TIMEOUT_MS = 10_000;
const PAID_TIMEOUT_MS = 60_000;

type Check = {
  name: string;
  paid: boolean;
  run: (baseUrl: string) => Promise<string>;
};

async function request(baseUrl: string, path: string, init: RequestInit, timeoutMs: number) {
  const response = await fetch(new URL(path, baseUrl), {
    ...init,
    signal: AbortSignal.timeout(timeoutMs),
  });
  const body: unknown = await response.json().catch(() => null);
  return { status: response.status, body };
}

function expectStatus(actual: number, expected: number) {
  if (actual !== expected) throw new Error(`expected ${expected}, got ${actual}`);
}

function hasStringField(body: unknown, field: string): body is Record<string, string> {
  return (
    typeof body === "object" &&
    body !== null &&
    typeof (body as Record<string, unknown>)[field] === "string"
  );
}

const checks: Check[] = [
  {
    name: "GET /health",
    paid: false,
    run: async (baseUrl) => {
      const { status, body } = await request(baseUrl, "/health", {}, FREE_TIMEOUT_MS);
      expectStatus(status, 200);
      if (!hasStringField(body, "status") || body.status !== "ok")
        throw new Error('body is not {"status":"ok"}');
      return "200 ok";
    },
  },
  {
    name: "GET unknown route",
    paid: false,
    run: async (baseUrl) => {
      const { status, body } = await request(
        baseUrl,
        "/smoke-test-missing-route",
        {},
        FREE_TIMEOUT_MS
      );
      expectStatus(status, 404);
      if (!hasStringField(body, "error")) throw new Error("body has no error message");
      return "404 JSON error";
    },
  },
  {
    name: "POST /recommend invalid body",
    paid: false,
    run: async (baseUrl) => {
      const { status, body } = await request(
        baseUrl,
        "/recommend",
        { method: "POST", headers: { "content-type": "application/json" }, body: "{}" },
        FREE_TIMEOUT_MS
      );
      expectStatus(status, 400);
      if (!hasStringField(body, "error")) throw new Error("body has no error message");
      return "400 validation error";
    },
  },
  {
    name: "POST /recommend real request",
    paid: true,
    run: async (baseUrl) => {
      const { status, body } = await request(
        baseUrl,
        "/recommend",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            turns: [
              {
                role: "user",
                content: "I live in Canada and want a free app to track my monthly budget",
              },
            ],
          }),
        },
        PAID_TIMEOUT_MS
      );
      expectStatus(status, 200);
      if (
        !hasStringField(body, "type") ||
        !["recommendation", "clarification"].includes(body.type)
      ) {
        throw new Error("response type is not recommendation or clarification");
      }
      return `200 ${body.type}`;
    },
  },
];

function parseArgs(argv: string[]) {
  const skipPaid = argv.includes("--skip-paid");
  const target = argv.find((arg) => !arg.startsWith("--"));
  if (!target) {
    console.error("Usage: npm run smoke -- <base-url> [--skip-paid]");
    process.exit(1);
  }
  try {
    return { baseUrl: new URL(target).toString(), skipPaid };
  } catch {
    console.error(`Not a valid URL: ${target}`);
    process.exit(1);
  }
}

async function main() {
  const { baseUrl, skipPaid } = parseArgs(process.argv.slice(2));
  let failures = 0;

  console.log(
    `Smoke testing ${new URL(baseUrl).origin}${skipPaid ? " (skipping paid checks)" : ""}`
  );

  for (const check of checks) {
    if (check.paid && skipPaid) {
      console.log(`  SKIP  ${check.name}`);
      continue;
    }
    try {
      console.log(`  PASS  ${check.name} — ${await check.run(baseUrl)}`);
    } catch (error) {
      failures += 1;
      const message = error instanceof Error ? error.message : String(error);
      console.log(`  FAIL  ${check.name} — ${message}`);
    }
  }

  console.log(failures === 0 ? "All checks passed." : `${failures} check(s) failed.`);
  process.exit(failures === 0 ? 0 : 1);
}

void main();
