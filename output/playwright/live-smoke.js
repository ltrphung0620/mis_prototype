// Real FastAPI, production frontend build, original TeamPack, memory DB, OpenAI off.
// Starts only the ordinary evaluation; no protected approval is submitted.
async (page) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("http://127.0.0.1:8000/dashboard");
  await page.getByRole("button", { name: "Bắt đầu đánh giá", exact: true }).click();
  const review = page.getByRole("dialog", { name: "Decision Card" });
  await review.waitFor();
  if (await review.getByRole("button", { name: "Phê duyệt", exact: true }).count()) throw new Error("OpenAI-off NOT_EVALUABLE review must be read-only");
  await review.getByRole("button", { name: "Đóng", exact: true }).click();
  await page.getByRole("button", { name: "Đánh giá", exact: true }).click();
  await page.getByRole("heading", { name: "Cơ sở đánh giá", exact: true }).waitFor();
  await page.getByRole("button", { name: "Bằng chứng", exact: true }).click();
  await page.getByRole("heading", { name: "Hồ sơ & bằng chứng", exact: true }).waitFor();
  await page.locator(".evidence-table tbody tr").first().waitFor();
  if (await page.getByRole("row").count() <= 1) throw new Error("Real workflow artifacts should be visible");
  await page.getByRole("button", { name: "Đánh giá", exact: true }).click();
  await page.screenshot({ path: "output/playwright/founder-live-assessments.png", fullPage: true });
  await page.getByRole("button", { name: "Quyết định", exact: true }).click();
  await page.screenshot({ path: "output/playwright/founder-live-workspace.png", fullPage: true });
}
