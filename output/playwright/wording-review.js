async (page) => {
  const base = 'http://127.0.0.1:5183/dashboard-assets/?preview=1';
  const root = 'D:/UIT/Project/AISC2026/mis_prototype/output/playwright/';
  const rows = [], errors = [], apiCalls = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (new URL(request.url()).pathname.startsWith('/api/')) apiCalls.push(request.url());
  });
  const routes = [
    '/dashboard', '/company', '/company?section=finance&period=recent',
    '/company?section=business', '/company?section=invoices', '/company?section=alerts',
    '/contracts', '/contracts/CON-004', '/contracts/CON-004?view=assessments',
    '/contracts/CON-004?view=evidence', '/contracts/CON-004?view=history',
    '/contracts/CON-004?view=workflow', '/contracts/CON-003?view=workflow',
  ];
  for (const width of [390, 768, 1440, 1920]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const route of routes) {
      await page.goto(base + '#' + route);
      await page.locator('.pv-main h1').waitFor();
      if (route.includes('view=workflow')) await page.locator('.wf-viewer, .wf-no-run').waitFor();
      await page.evaluate(async () => {
        await document.fonts.ready;
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      });
      const measurement = await page.evaluate(() => ({
        width: innerWidth, pageWidth: document.documentElement.scrollWidth,
        overflow: document.documentElement.scrollWidth > innerWidth + 1,
        technicalCopy: /\bbackend\b|\bfixtures?\b|Bản xem trước|\bSnapshot\b|Execution status|Pending interaction|\bGate\b|\bnodes\b|\bconnections\b|\binspector\b|Fit view|AI RECOMMENDATION|DETERMINISTIC SYSTEM ANALYSIS/.test(document.body.innerText),
        missingSimulation: !document.body.innerText.includes('Dữ liệu mô phỏng'),
      }));
      rows.push({ width, route, ...measurement });
      if ((width === 390 && route === '/company?section=invoices') ||
          (width === 1440 && route === '/contracts/CON-004?view=workflow') ||
          (width === 1440 && route === '/dashboard')) {
        const name = route.includes('invoices') ? 'invoices' : route.includes('workflow') ? 'workflow' : 'dashboard';
        await page.screenshot({ path: root + `wording-${name}-${width}.png`, fullPage: true });
      }
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(base + '#/contracts/CON-004?request=UI-APPROVAL-CON-004');
  const modal = page.getByRole('dialog');
  await modal.waitFor();
  rows.push({ check: 'mobile-dialog', ...(await page.evaluate(() => ({
    overflow: document.documentElement.scrollWidth > innerWidth + 1,
    dialogWidth: document.querySelector('[role=dialog]').getBoundingClientRect().width,
  }))) });
  await page.screenshot({ path: root + 'wording-review-390.png', fullPage: true });
  await page.getByRole('button', { name: 'Phê duyệt', exact: true }).click();
  if (!await modal.getByText('Đã mô phỏng thao tác phê duyệt.', { exact: false }).isVisible()) throw new Error('Missing simulated-submit result');
  if (!await modal.getByRole('button', { name: 'Phê duyệt', exact: true }).isDisabled()) throw new Error('Duplicate submit guard missing');
  await page.keyboard.press('Escape');
  await page.goto(base + '#/contracts/CON-004?view=workflow');
  await page.getByRole('heading', { name: 'Quy trình xử lý', exact: true }).waitFor();
  await page.locator('.wf-list button').filter({ hasText: 'Duyệt quyết định' }).click();
  await page.getByRole('complementary', { name: 'Chi tiết bước Duyệt quyết định' }).waitFor();
  await page.screenshot({ path: root + 'wording-inspector-390.png', fullPage: true });
  await page.keyboard.press('Escape');
  rows.push({ check: 'mobile-inspector-escape', closed: await page.locator('.wf-inspector').count() === 0 });
  return { rows, errors, apiCalls, failures: rows.filter(row => row.overflow || row.technicalCopy || row.missingSimulation) };
}
