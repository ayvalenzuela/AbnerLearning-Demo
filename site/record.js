// Records a screen video of each build's step-by-step replay: node site/record.js 01 02 ...
// Needs the site served at http://localhost:8765 (python -m http.server 8765 in site/).
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path"), { execFileSync } = require("child_process");
const OUT = path.join(__dirname, "videos"), TMP = process.env.REC_TMP || path.join(__dirname, ".rec");
(async () => {
  fs.mkdirSync(OUT, { recursive: true }); fs.mkdirSync(TMP, { recursive: true });
  const ids = process.argv.slice(2);
  const browser = await chromium.launch();
  for (const id of ids) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, recordVideo: { dir: TMP, size: { width: 1280, height: 800 } }, colorScheme: "light" });
    const page = await ctx.newPage();
    await page.goto(`http://localhost:8765/#build-${id}`);
    await page.waitForFunction(() => window.__ready);
    await page.evaluate(() => { document.body.classList.add("rec"); window.scrollTo(0, 0); });
    await page.waitForTimeout(1500);
    await page.click("#play");
    await page.waitForFunction(() => window.__done === true, null, { timeout: 240000 });
    await page.waitForTimeout(1500);
    const v = page.video(); await ctx.close();
    const webm = await v.path();
    const mp4 = path.join(OUT, `build-${id}.mp4`);
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-ss", "2", "-i", webm, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "30", "-preset", "slow", "-movflags", "+faststart", mp4]);
    console.log("wrote", mp4, (fs.statSync(mp4).size / 1e6).toFixed(1) + "MB");
  }
  await browser.close();
})();
