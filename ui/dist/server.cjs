var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));

// server.ts
var import_express = __toESM(require("express"), 1);
var import_path = __toESM(require("path"), 1);
var import_dotenv = require("dotenv");
var import_vite = require("vite");
var import_http_proxy_middleware = require("http-proxy-middleware");
var __dirname = process.cwd();
(0, import_dotenv.config)({ path: import_path.default.resolve(__dirname, "../.env") });
var app = (0, import_express.default)();
var PORT = Number(process.env.PORT || 3e3);
var jsonBodyParser = import_express.default.json({ limit: "15mb" });
var FASTAPI_URL = process.env.FASTAPI_URL || "http://localhost:8080";
function parseLinkedInProfileName(linkedinUrl) {
  const slug = linkedinUrl.replace(/\/$/, "").split("/").pop() || "";
  const words = slug.split(/[-_.]+/).filter(Boolean);
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ") || "LinkedIn Candidate";
}
function isLinkedInProfileUrl(linkedinUrl) {
  return /^https:\/\/(?:www\.)?linkedin\.com\/in\/[^/\s]+\/?$/.test(linkedinUrl.trim());
}
async function forwardToFastAPI(req, res, apiPath) {
  try {
    const backend = await fetch(`${FASTAPI_URL}${apiPath}`, {
      method: req.method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body)
    });
    const payload = await backend.text();
    res.status(backend.status).type(backend.headers.get("content-type") || "application/json").send(payload);
  } catch (error) {
    res.status(502).json({
      error: "FastAPI backend unavailable.",
      details: error.message || String(error)
    });
  }
}
app.get("/api/health", (_req, res) => {
  res.json({
    status: "ok",
    timestamp: (/* @__PURE__ */ new Date()).toISOString(),
    fastapiUrl: FASTAPI_URL
  });
});
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
      complianceStatus: "PENDING REVIEW"
    }
  });
});
app.use(
  "/api",
  (0, import_http_proxy_middleware.createProxyMiddleware)({
    target: FASTAPI_URL,
    changeOrigin: true,
    pathRewrite: { "^/": "/api/" },
    on: {
      error: (_err, _req, res) => {
        res.status(502).json({
          error: "FastAPI backend unavailable. Start it with: uvicorn web.app:app --port 8080"
        });
      }
    }
  })
);
async function start() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await (0, import_vite.createServer)({
      server: { middlewareMode: true },
      appType: "spa"
    });
    app.use(vite.middlewares);
  } else {
    const distPath = import_path.default.join(process.cwd(), "dist");
    app.use(import_express.default.static(distPath));
    app.get("*", (_req, res) => {
      res.sendFile(import_path.default.join(distPath, "index.html"));
    });
  }
  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Linnify Talent Pool UI running on http://0.0.0.0:${PORT}`);
  });
}
start();
//# sourceMappingURL=server.cjs.map
