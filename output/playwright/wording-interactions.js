async (page) => {
  const base = 'http://127.0.0.1:5183/dashboard-assets/?preview=1';
  const results = [];
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(base + '#/company?section=invoices&status=Paid&period=recent');
  await page.getByRole('combobox', { name: 'Trạng thái hóa đơn' }).waitFor();
  await page.evaluate(() => window.scrollTo(0, 100));
  const before = await page.evaluate(() => window.scrollY);
  await page.getByRole('combobox', { name: 'Trạng thái hóa đơn' }).selectOption('Open');
  await page.waitForURL(/status=Open/);
  const after = await page.evaluate(() => window.scrollY);
  if (before !== after) throw new Error(`Filter moved page: ${before} -> ${after}`);
  if (await page.locator('tbody').last().innerText().then(text => text.includes('INV-001'))) throw new Error('Invoice filter leaked Paid record');
  results.push({ check: 'raw-status-filter-and-scroll', before, after, status: new URL(page.url().split('#')[1], 'http://local').searchParams.get('status') });
  await page.getByRole('link', { name: 'Tài chính', exact: true }).click();
  await page.waitForURL(/section=finance/);
  if (!page.url().includes('period=recent')) throw new Error('Period lost between tabs');
  results.push({ check: 'company-period-preserved', period: await page.getByRole('combobox', { name: 'Kỳ biểu đồ dòng tiền' }).inputValue() });
  await page.goto(base + '#/company?section=alerts');
  await page.getByRole('link', { name: 'Cảnh báo & giới hạn', exact: true }).waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  results.push({ check: 'active-mobile-tab', ...(await page.locator('.pv-tabs').evaluate(nav => {
    const active = nav.querySelector('a[aria-current=page]');
    const n = nav.getBoundingClientRect(), a = active.getBoundingClientRect();
    return { left: a.left, right: a.right, fullyVisible: a.left >= n.left - 1 && a.right <= n.right + 1 };
  })) });
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const scenario of ['approval','assessment','banking','document','input','failed','completed','negotiation','release']) {
      await page.goto(base + `#/contracts/CON-004?view=workflow&scenario=${scenario}&phase=all`);
      await page.getByRole('heading', { name: 'Quy trình xử lý', exact: true }).waitFor();
      results.push({ width, scenario, ...(await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth > innerWidth + 1,
        technicalCopy: /\bGate\b|\bnodes\b|\bconnections\b|\binspector\b|\bbackend\b|\bfixtures?\b|Fit view|\bCard\b|Tài chínhFacts|\bauthorization\b|\bapplicability\b/.test(document.body.innerText),
      }))) });
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(base + '#/contracts/CON-004?view=workflow&phase=decision');
  await page.getByRole('region', { name: 'Sơ đồ quy trình chỉ xem' }).waitFor();
  const zoom = page.getByLabel('Mức phóng to');
  const zoomBefore = await zoom.innerText();
  await page.getByRole('button', { name: 'Phóng to quy trình', exact: true }).click();
  const zoomAfter = await zoom.innerText();
  await page.getByRole('button', { name: 'Vừa khung', exact: true }).click();
  results.push({ check: 'diagram-controls', zoomBefore, zoomAfter, changed: zoomBefore !== zoomAfter });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 720, height: 500 });
  await page.goto(base + '#/contracts/CON-004?request=UI-APPROVAL-CON-004');
  await page.getByRole('dialog').waitFor();
  const modal = await page.getByRole('dialog').innerText();
  results.push({ check: 'reduced-motion-and-narrow-dialog', technicalCopy: /AI RECOMMENDATION|DETERMINISTIC SYSTEM ANALYSIS|\bbackend\b|\bfixtures?\b/.test(modal), ...(await page.evaluate(() => ({ overflow: document.documentElement.scrollWidth > innerWidth + 1 }))) });
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  return { results, failures: results.filter(item => item.overflow || item.technicalCopy || item.fullyVisible === false || item.changed === false) };
}
