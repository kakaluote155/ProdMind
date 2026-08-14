const fs = require("node:fs");
const path = require("node:path");

const playwrightModule = process.env.PRODMIND_PLAYWRIGHT_MODULE || "playwright";
const { chromium } = require(playwrightModule);

async function main() {
  const output = path.resolve(process.argv[2] || "release/demo-frames");
  fs.mkdirSync(output, { recursive: true });
  const executablePath = process.env.PRODMIND_BROWSER_PATH || undefined;
  const browser = await chromium.launch({ headless: true, executablePath });
  try {
    const page = await browser.newPage({ viewport: { width: 1200, height: 760 } });
    await page.goto("http://localhost:8090", { waitUntil: "networkidle" });
    await page.screenshot({ path: path.join(output, "01-demo.png") });

    await page.locator("#createBtn").click();
    await page.locator("#status").filter({ hasText: "Operation failed" }).waitFor();
    await page.screenshot({ path: path.join(output, "02-failure.png") });

    let diagnosed = false;
    for (let attempt = 0; attempt < 12; attempt += 1) {
      await page.waitForTimeout(attempt === 0 ? 5000 : 2000);
      await page.locator("#askBtn").click();
      try {
        await page.locator(".root-cause").waitFor({ timeout: 8000 });
        diagnosed = true;
        break;
      } catch {
        await page.locator("#askBtn:not([disabled])").waitFor({ timeout: 3000 });
      }
    }
    if (!diagnosed) throw new Error("ProdMind did not diagnose the demo trace in time");
    await page.screenshot({ path: path.join(output, "03-answer.png") });

    const bodyText = await page.locator("body").innerText();
    for (const forbidden of ["trace_id", "uk_user_phone", "DuplicateKeyException"] ) {
      if (bodyText.includes(forbidden)) {
        throw new Error(`customer demo screenshot would expose forbidden value: ${forbidden}`);
      }
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
