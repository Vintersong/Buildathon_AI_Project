import express from "express";
import path from "path";
import { config as loadDotenv } from "dotenv";
import { createServer as createViteServer } from "vite";
import { createProxyMiddleware } from "http-proxy-middleware";

const __dirname = process.cwd();

// Load .env from project root (one level above ui/).
loadDotenv({ path: path.resolve(__dirname, "../.env") });

const app = express();
const PORT = Number(process.env.PORT || 3000);
const jsonBodyParser = express.json({ limit: "15mb" });
const FASTAPI_URL = process.env.FASTAPI_URL || "http://localhost:8080";
const API_TOKEN = process.env.TALENT_POOL_API_TOKEN || process.env.APP_API_TOKEN || "";

function parseLinkedInProfileName(linkedinUrl: string): string {
  const slug = linkedinUrl.replace(/\/$/, "").split("/").pop() || "";
  const words = slug.split(/[-_.]+/).filter(Boolean);
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ") || "LinkedIn Candidate";
}

function isLinkedInProfileUrl(linkedinUrl: string): boolean {
  return /^https:\/\/(?:www\.)?linkedin\.com\/in\/[^/\s]+\/?$/.test(linkedinUrl.trim());
}

async function forwardToFastAPI(req: express.Request, res: express.Response, apiPath: string) {
  try {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (API_TOKEN) {
      headers["X-API-Token"] = API_TOKEN;
    }
    const backend = await fetch(`${FASTAPI_URL}${apiPath}`, {
      method: req.method,
      headers,
      body: JSON.stringify(req.body),
    });
    const payload = await backend.text();
    res.status(backend.status).type(backend.headers.get("content-type") || "application/json").send(payload);
  } catch (error: any) {
    res.status(502).json({
      error: "FastAPI backend unavailable.",
      details: error.message || String(error),
    });
  }
}

app.get("/api/health", (_req, res) => {
  res.json({
    status: "ok",
    timestamp: new Date().toISOString(),
    fastapiUrl: FASTAPI_URL,
  });
});

// FastAPI owns LLM routing so dev and production both honor config.json,
// including the LM Studio / Gemma local-model toggle.
app.post("/api/gemini/chat", jsonBodyParser, async (req, res) => {
  await forwardToFastAPI(req, res, "/api/gemini/chat");
});

app.post("/api/gemini/parse-cv", jsonBodyParser, async (req, res) => {
  await forwardToFastAPI(req, res, "/api/gemini/parse-cv");
});

app.post("/api/gemini/parse-linkedin", jsonBodyParser, async (req, res) => {
  const { linkedinUrl } = req.body;
  if (!linkedinUrl || typeof linkedinUrl !== "string" || !isLinkedInProfileUrl(linkedinUrl)) {
    res.status(400).json({ error: "Please provide a valid https://linkedin.com/in/... profile URL." });
    return;
  }

  res.json({
    candidate: {
      name: parseLinkedInProfileName(linkedinUrl.trim()),
      seniority: "LinkedIn profile",
      topSkills: ["LINKEDIN"],
      matchScore: 0.5,
      complianceStatus: "PENDING REVIEW",
    },
  });
});

// Proxy all other /api/* requests to the FastAPI backend.
app.use(
  "/api",
  createProxyMiddleware({
    target: FASTAPI_URL,
    changeOrigin: true,
    pathRewrite: { "^/": "/api/" },
    on: {
      proxyReq: (proxyReq) => {
        if (API_TOKEN) {
          proxyReq.setHeader("X-API-Token", API_TOKEN);
        }
      },
      error: (_err: Error, _req: express.Request, res: express.Response) => {
        (res as express.Response).status(502).json({
          error: "FastAPI backend unavailable. Start it with: uvicorn web.app:app --port 8080",
        });
      },
    },
  })
);

async function start() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (_req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Linnify Talent Pool UI running on http://0.0.0.0:${PORT}`);
  });
}

start();
