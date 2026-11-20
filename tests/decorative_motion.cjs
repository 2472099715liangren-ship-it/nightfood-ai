/* Optional browser check: start the app, then run with Playwright available. */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 900 },
      reducedMotion: "no-preference",
    });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("https://**/*", (route) => route.abort());
    const url = process.argv[2] || "http://127.0.0.1:8000";
    await page.goto(url);
    await page.locator("#request-message:not([disabled])").waitFor();
    const control = page.locator("[data-decoration-toggle]");
    const sample = () =>
      page.evaluate(() => ({
        stem: getComputedStyle(
          document.querySelector(".botanical-left"),
          "::before",
        ).transform,
        leaf: getComputedStyle(document.querySelector(".leaf-one")).transform,
        glow: getComputedStyle(
          document.querySelector(".botanical-left"),
          "::after",
        ).opacity,
        spark: getComputedStyle(document.querySelector(".spark-one")).transform,
        background: getComputedStyle(document.body, "::before").transform,
      }));
    const first = await sample();
    await page.waitForTimeout(700);
    assert.notDeepEqual(
      await sample(),
      first,
      "Decorations should actually move",
    );
    assert.ok(
      await page
        .locator(".botanical-right")
        .evaluate((el) =>
          getComputedStyle(el).transform.startsWith("matrix(-1,"),
        ),
      "Right side stays mirrored",
    );
    assert.equal(
      await page.locator(".side-botanical").first().getAttribute("aria-hidden"),
      "true",
    );
    assert.equal(
      await page
        .locator(".side-botanical")
        .first()
        .evaluate((el) => getComputedStyle(el).pointerEvents),
      "none",
    );
    await control.click();
    await control.filter({ hasText: "开启装饰动效" }).waitFor();
    const paused = await sample();
    await page.waitForTimeout(600);
    assert.deepEqual(
      await sample(),
      paused,
      "Pause should freeze every decoration layer",
    );
    await page.reload();
    await page.locator("#request-message:not([disabled])").waitFor();
    assert.equal(await control.innerText(), "开启装饰动效");
    assert.ok(
      await page
        .locator("body")
        .evaluate((el) => el.classList.contains("decorations-paused")),
    );
    await control.click();
    const resumed = await sample();
    await page.waitForTimeout(600);
    assert.notDeepEqual(await sample(), resumed);

    await page.emulateMedia({ reducedMotion: "reduce" });
    await control.filter({ hasText: "随系统关闭" }).waitFor();
    assert.ok(await control.isDisabled());
    assert.equal(
      await page
        .locator("body")
        .evaluate((el) => getComputedStyle(el, "::before").animationName),
      "none",
    );
    assert.equal(
      await page
        .locator(".botanical-left")
        .evaluate((el) => getComputedStyle(el, "::before").animationName),
      "none",
    );
    assert.ok(
      await page
        .locator(".botanical-left")
        .evaluate((el) =>
          getComputedStyle(el, "::before").maskImage.includes("botanical.svg"),
        ),
      "Static botanical artwork remains available",
    );
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await control.filter({ hasText: "暂停装饰动效" }).waitFor();

    // Background visibility uses the same pause state without persisting a manual pause.
    await page.evaluate(() => {
      Object.defineProperty(document, "hidden", {
        configurable: true,
        value: true,
      });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    assert.ok(
      await page
        .locator("body")
        .evaluate((el) => el.classList.contains("decorations-paused")),
    );
    await page.evaluate(() => {
      delete document.hidden;
      document.dispatchEvent(new Event("visibilitychange"));
    });
    assert.equal(await control.innerText(), "暂停装饰动效");

    for (const width of [1440, 1366, 1280, 1100, 1024, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `overflow at ${width}`,
      );
      assert.equal(
        await page.locator(".side-botanical").first().isVisible(),
        width > 1100,
      );
      assert.ok(
        await control.isVisible(),
        "Background motion can be paused at every width",
      );
    }
    await page.locator("#request-message").scrollIntoViewIfNeeded();
    assert.ok(
      await page.locator("#request-message").evaluate((el) => {
        const r = el.getBoundingClientRect();
        return (
          document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2) ===
          el
        );
      }),
      "Decorations cannot cover the chat input",
    );
    assert.deepEqual(errors, []);

    // Private browsing may deny storage; the visual control still works for this tab.
    const privatePage = await browser.newPage({
      viewport: { width: 1440, height: 900 },
    });
    await privatePage.addInitScript(() => {
      const originalGet = Storage.prototype.getItem;
      const originalSet = Storage.prototype.setItem;
      Storage.prototype.getItem = function (key) {
        if (key === "nightfind-decoration-motion")
          throw Error("storage unavailable");
        return originalGet.call(this, key);
      };
      Storage.prototype.setItem = function (key, value) {
        if (key === "nightfind-decoration-motion")
          throw Error("storage unavailable");
        return originalSet.call(this, key, value);
      };
    });
    await privatePage.route("https://**/*", (route) => route.abort());
    await privatePage.goto(url);
    await privatePage.locator("#request-message:not([disabled])").waitFor();
    await privatePage.locator("[data-decoration-toggle]").click();
    assert.equal(
      await privatePage.locator("[data-decoration-toggle]").innerText(),
      "开启装饰动效",
    );
    await privatePage.close();
    console.log(
      "PASS: actual animation, mirrored margins, pause/resume and persistence, reduced motion, visibility pause, unavailable storage, responsive widths and unobstructed chat input.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
