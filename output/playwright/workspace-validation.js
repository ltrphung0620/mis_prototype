// Run after mercury-review.js; UI fixtures only, protected mutations are blocked.
async (page) => {
  const assert = (value, message) => { if (!value) throw new Error(message); };
  const checks = [];
  for (const width of [390, 768, 1440, 1920]) {
    await page.setViewportSize({ width, height: width < 760 ? 844 : 1080 });
    await page.getByRole("button", { name: "Quyết định", exact: true }).click();
    const size = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    assert(size.scroll <= size.width, `Page overflow at ${width}: ${JSON.stringify(size)}`);
    checks.push({ viewport: width, pageOverflow: false });
    if (width === 390) await page.screenshot({ path: "output/playwright/founder-mobile.png", fullPage: true });
  }
  await page.getByRole("button", { name: "Bằng chứng", exact: true }).click();
  await page.getByRole("heading", { name: "Hồ sơ & bằng chứng" }).waitFor();
  assert(await page.getByRole("row").count() === 7, "Evidence table must include current-run artifacts only");
  await page.screenshot({ path: "output/playwright/founder-evidence.png", fullPage: true });
  await page.getByRole("button", { name: "Quy trình", exact: true }).click();
  await page.getByRole("cell", { name: "NODE_COMPLETED", exact: true }).waitFor();
  await page.getByRole("button", { name: "Quyết định", exact: true }).click();
  const opener = page.getByRole("button", { name: "Xem Decision Card hiện hành" });
  await opener.click();
  const dialog = page.getByRole("dialog", { name: "Decision Card" });
  await dialog.waitFor();
  assert(await dialog.getByRole("button", { name: "Phê duyệt", exact: true }).isEnabled(), "Exact approval should be available in review only");
  assert(await page.evaluate(() => !!document.activeElement.closest('[role="dialog"]')), "Focus must move into review dialog");
  await page.screenshot({ path: "output/playwright/founder-decision-review.png", fullPage: false });
  await dialog.getByRole("button", { name: "Đóng", exact: true }).focus();
  await page.keyboard.press("Tab");
  assert(await page.evaluate(() => !!document.activeElement.closest('[role="dialog"]')), "Tab must remain in review dialog");
  await page.keyboard.press("Escape");
  assert(await dialog.count() === 0, "Escape should close review");
  assert(await opener.evaluate((element) => element === document.activeElement), "Focus should return to opener");
  await opener.evaluate((element) => element.blur());
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: "output/playwright/founder-desktop.png", fullPage: true });
  console.log(JSON.stringify({ checks, evidence: "6 current artifacts", workflowLog: "loaded", exactApprovalReview: "enabled, not submitted", keyboard: "focus/Tab/Escape/restore passed" }));
}
