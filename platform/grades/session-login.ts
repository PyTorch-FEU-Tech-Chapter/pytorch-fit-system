import { chromium } from "playwright";

import { FEU_SOLAR } from "./scraper";

const output = process.argv[2] ?? ".cache/feu-solar-storage-state.json";
const browser = await chromium.launch({ headless: false });
const context = await browser.newContext();
const page = await context.newPage();

console.log("Complete the FEU/Microsoft login in the browser window.");
await page.goto(FEU_SOLAR.gradesUrl, { waitUntil: "domcontentloaded" });
await page.waitForURL((url) => url.hostname === "solar.feutech.edu.ph", { timeout: 10 * 60_000 });
await page.goto(FEU_SOLAR.gradesUrl, { waitUntil: "networkidle" });
await context.storageState({ path: output });
console.log(`FEU session saved to ${output}`);
await browser.close();
