/* Optional browser regression: start the app, then run with Playwright available.
 * CHROMIUM_PATH=/usr/bin/chromium node tests/recommendation_navigation.cjs http://127.0.0.1:8000
 */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const { mkdirSync } = require("node:fs");
const { join } = require("node:path");

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1050 },
    });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("https://**/*", (route) => route.abort());
    await page.goto(process.argv[2] || "http://127.0.0.1:8000");
    await page.locator("#request-message:not([disabled])").waitFor();
    const snapshot = async (name) => {
      if (!process.env.SCREENSHOT_DIR) return;
      mkdirSync(process.env.SCREENSHOT_DIR, { recursive: true });
      await page.screenshot({
        path: join(process.env.SCREENSHOT_DIR, name),
        fullPage: true,
      });
    };
    const send = async (message) => {
      await page.locator("#request-message").fill(message);
      const response = page.waitForResponse((r) =>
        r.url().endsWith("/api/decision"),
      );
      await page.locator('#decision-form button[type="submit"]').click();
      return (await response).json();
    };
    const backToChat = async () => {
      await page.locator('.main-nav [data-page="decision"]').click();
      await page.locator("#request-message:not([disabled])").waitFor();
    };
    const expectRecommendations = async (result) => {
      assert.equal(result.stage, "candidates");
      assert.ok(result.items.length > 0);
      await page.locator("#recommendations-title").waitFor();
      await page
        .locator('.main-nav [data-page="recommendations"].active')
        .waitFor();
      assert.equal(await page.locator("#conversation-log").count(), 0);
      assert.deepEqual(
        await page
          .locator("[data-card]")
          .evaluateAll((cards) =>
            cards.map((card) => Number(card.dataset.card)),
          ),
        result.items.map((item) => item.id),
      );
      assert.match(
        await page.locator("#toast.visible").innerText(),
        /^推荐成功/,
      );
      await page.waitForFunction(() => {
        const title = document.getElementById("recommendations-title");
        const bounds = title?.getBoundingClientRect();
        return (
          bounds &&
          bounds.top >= 0 &&
          bounds.bottom <= innerHeight &&
          document.activeElement === title
        );
      });
    };

    // Clarification and a factual lookup remain in the conversation.
    const clarify = await send("我想找个地方吃晚饭");
    assert.equal(clarify.stage, "clarify");
    await page.locator("#request-message:not([disabled])").waitFor();
    assert.equal(await page.locator("#recommendations-title").count(), 0);
    assert.equal(await page.locator("#toast.visible").count(), 0);
    const lookup = await send("查金贵源的菜单价格");
    assert.equal(lookup.stage, "catalog");
    await page.locator("[data-card]").first().waitFor();
    assert.equal(await page.locator("#recommendations-title").count(), 0);

    const plan = "明天晚上七点，两个人在江汉路附近，总预算400元，想吃湖北菜";
    let result = await send(plan);
    await expectRecommendations(result);
    await snapshot("recommendations-desktop.png");

    // Existing card actions work without leaving the recommended list.
    const firstId = result.items[0].id;
    await page.locator(`[data-detail="${firstId}"]`).click();
    await page.getByRole("dialog").waitFor();
    assert.ok(
      (await page.locator("#merchant-detail").innerText()).includes(
        result.items[0].name,
      ),
    );
    await page.locator("[data-close]").click();
    await page.locator("[data-show-map]").click();
    await page.locator('#decision-map[data-basemap="ready"]').waitFor();
    assert.equal(
      Number(await page.locator("#decision-map").getAttribute("data-pins")),
      result.items.filter(
        (item) => item.latitude != null && item.longitude != null,
      ).length,
    );
    await page.locator(`[data-save="${firstId}"]`).click();
    await page
      .locator(`[data-save="${firstId}"][aria-pressed="true"]`)
      .waitFor();
    for (const item of result.items.slice(0, 2)) {
      await page.locator(`[data-compare="${item.id}"]`).click();
      await page
        .locator(`[data-compare="${item.id}"][aria-pressed="true"]`)
        .waitFor();
    }
    await page.locator("[data-open-compare]").click();
    await page.locator("dialog[open] table").waitFor();
    await page.locator("[data-close]").click();
    await page.locator("[data-clear-compare]").click();
    await page.locator(`[data-card="${firstId}"] [data-choose]`).click();
    await page.locator("#selected-place:not([hidden])").waitFor();
    assert.ok(
      (await page.locator("#selected-place").innerText()).includes(
        result.items[0].name,
      ),
    );
    assert.ok(
      await page.locator('#selected-place a[href*="uri.amap.com"]').count(),
    );
    assert.ok(await page.locator("#recommendations-title").isVisible());

    // Refresh reloads facts and restores the page without another success toast.
    await page.reload();
    await page.locator("#recommendations-title").waitFor();
    assert.equal(await page.locator("#toast.visible").count(), 0);
    await backToChat();
    assert.ok(
      (await page.locator("#conversation-log").innerText()).includes(plan),
    );

    // Structured edits use the same success-and-navigation behavior.
    await page.locator(".conditions [data-edit-needs]").click();
    await page.locator('#preferences-form [name="budget"]').fill("120");
    const editedResponse = page.waitForResponse((r) =>
      r.url().endsWith("/api/decision"),
    );
    await page.locator('#preferences-form button[type="submit"]').click();
    result = await (await editedResponse).json();
    assert.equal(result.budget_per_person, 60);
    await expectRecommendations(result);

    // A real empty result must not reuse the preceding success toast.
    await backToChat();
    await page.locator(".conditions [data-edit-needs]").click();
    await page
      .locator('#preferences-form [name="location_name"]')
      .fill("汉南区");
    const emptyResponse = page.waitForResponse((r) =>
      r.url().endsWith("/api/decision"),
    );
    await page.locator('#preferences-form button[type="submit"]').click();
    const empty = await (await emptyResponse).json();
    assert.equal(empty.items.length, 0);
    await page.locator("#request-message:not([disabled])").waitFor();
    assert.equal(await page.locator("#recommendations-title").count(), 0);
    assert.equal(await page.locator("#toast.visible").count(), 0);

    // Failure followed by retry only redirects when the retry actually succeeds.
    result = await send(plan);
    await expectRecommendations(result);
    await backToChat();
    await page.route("**/api/decision", (route) => route.abort());
    await page.locator("#request-message").fill("便宜一点");
    await page.locator('#decision-form button[type="submit"]').click();
    await page.locator("[data-retry-decision]").waitFor();
    assert.equal(await page.locator("#recommendations-title").count(), 0);
    assert.ok(!(await page.locator("#toast").innerText()).includes("推荐成功"));
    await page.unroute("**/api/decision");
    const retryResponse = page.waitForResponse((r) =>
      r.url().endsWith("/api/decision"),
    );
    await page.locator("[data-retry-decision]").click();
    result = await (await retryResponse).json();
    await expectRecommendations(result);

    // Navigating elsewhere while waiting is respected after a delayed response.
    await backToChat();
    let release;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    await page.route("**/api/decision", async (route) => {
      await gate;
      await route.continue();
    });
    await page.locator("#request-message").fill(plan);
    const delayedResponse = page.waitForResponse((r) =>
      r.url().endsWith("/api/decision"),
    );
    await page.locator('#decision-form button[type="submit"]').click();
    await page.locator(".thinking").waitFor();
    await page.locator('.main-nav [data-page="saved"]').click();
    await page.locator('.main-nav [data-page="saved"].active').waitFor();
    release();
    await delayedResponse;
    await page.unroute("**/api/decision");
    await page.locator("[data-card]").first().waitFor();
    assert.equal(await page.locator("#recommendations-title").count(), 0);
    assert.equal(await page.locator("#toast.visible").count(), 0);

    await backToChat();
    result = await send(plan);
    await expectRecommendations(result);
    for (const width of [320, 390, 700, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `overflow at ${width}px`,
      );
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => scrollTo({ top: 0, behavior: "instant" }));
    await snapshot("recommendations-mobile.png");
    assert.deepEqual(errors, []);
    console.log(
      "PASS: success toast and dedicated recommendation page, exact candidate IDs, clarification/lookup/empty/failure safeguards, retry, structured edits, refresh, history, card actions, delayed navigation and responsive layout.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
