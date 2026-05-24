import { chromium } from "playwright-core";
import { mkdirSync } from "fs";

const out = "D:/Buildat/Buildathon_AI_Project/ui/_test_shots";
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
});
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();

page.on("console", (m) => console.log("[console]", m.type(), m.text()));
page.on("pageerror", (e) => console.log("[pageerror]", e.message));
page.on("requestfailed", (r) => console.log("[reqfail]", r.url(), r.failure()?.errorText));

await page.goto("http://localhost:3000", { waitUntil: "networkidle", timeout: 30000 });
await page.screenshot({ path: `${out}/01_loaded.png`, fullPage: true });
console.log("Title:", await page.title());

// Try to find the AI Agent button/sidebar trigger
const candidates = await page.locator("button, [role=button]").allTextContents();
console.log("Buttons found:", candidates.slice(0, 30));

// Heuristics: look for an "AI" / "Agent" / "Assistant" button
const triggerSelectors = [
  'button:has-text("AI Agent")',
  'button:has-text("Agent")',
  'button:has-text("Assistant")',
  'button:has-text("AI")',
  '[aria-label*="agent" i]',
  '[aria-label*="assistant" i]',
  '[title*="agent" i]',
];
let opened = false;
for (const sel of triggerSelectors) {
  const loc = page.locator(sel).first();
  if ((await loc.count()) > 0) {
    console.log("Clicking trigger:", sel);
    try {
      await loc.click({ timeout: 3000 });
      opened = true;
      break;
    } catch (e) {
      console.log("Click failed:", e.message);
    }
  }
}
await page.waitForTimeout(500);
await page.screenshot({ path: `${out}/02_after_trigger.png`, fullPage: true });
console.log("Opened sidebar?", opened);

// Find a textbox/textarea inside the page
const inputSel = [
  'textarea',
  'input[type="text"]',
  '[contenteditable="true"]',
];
let typed = false;
for (const sel of inputSel) {
  const inputs = page.locator(sel);
  const n = await inputs.count();
  for (let i = 0; i < n; i++) {
    const el = inputs.nth(i);
    if (!(await el.isVisible())) continue;
    const ph = (await el.getAttribute("placeholder")) || "";
    console.log("Visible input", sel, "placeholder:", ph);
    try {
      await el.click();
      await el.fill(
        "What programming languages does Spreadsheet Candidate 3 know, and what is Andrei Moldovean's location and years of experience?"
      );
      await page.keyboard.press("Enter");
      typed = true;
      break;
    } catch (e) {
      console.log("Type failed:", e.message);
    }
  }
  if (typed) break;
}
console.log("Typed?", typed);

await page.waitForTimeout(15000); // wait for LLM response
await page.screenshot({ path: `${out}/03_after_send.png`, fullPage: true });

// Dump visible text of the page for evidence
const bodyText = await page.locator("body").innerText();
console.log("--- BODY TEXT (truncated) ---");
console.log(bodyText.slice(-3000));

await browser.close();
