async (page) => {
  const base = 'http://127.0.0.1:5173/dashboard-assets/?preview=1';
  const out = 'D:/UIT/Project/AISC2026/mis_prototype/output/playwright';
  const report = { checks: [], errors: [], apiRequests: [], measurements: [] };
  page.on('pageerror', e => report.errors.push(e.message));
  page.on('request', r => { if (new URL(r.url()).pathname.startsWith('/api/')) report.apiRequests.push(r.url()); });
  const check = (name, ok) => { if (!ok) throw new Error(name); report.checks.push(name); };
  for (const width of [1440, 1920, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1080 });
    await page.goto(base + '#/dashboard');
    await page.getByRole('button', {name:'Phê duyệt', exact:true}).click();
    check(`Action filter ${width}`, await page.locator('.pv-action-row').count() === 1);
    await page.getByRole('button', {name:'Tất cả', exact:true}).click();
    await page.locator('.recharts-cartesian-axis-tick-value').first().waitFor();
    await page.getByRole('application').focus(); await page.keyboard.press('ArrowRight');
    await page.locator('.pv-chart-tooltip').waitFor();
    check(`Readable VND tooltip ${width}`, await page.locator('.pv-chart-tooltip').innerText().then(t => /\d{1,3}(\.\d{3})+ VND/.test(t) && t.includes('tỷ VND')));
    const tooltipBox = await page.locator('.pv-chart-tooltip').boundingBox();
    check(`Tooltip inside viewport ${width}`, tooltipBox.x >= 0 && tooltipBox.x + tooltipBox.width <= width);
    await page.screenshot({path:`${out}/ui-polish-tooltip-${width}.png`,scale:'css'});
    await page.getByRole('combobox', {name:'Kỳ biểu đồ dòng tiền'}).selectOption('empty');
    await page.getByText('Chưa có dữ liệu dự kiến cho kỳ này. Không suy ra bằng 0.').waitFor();
    check(`Empty chart preserves unknown ${width}`, true);
    await page.goto(base + '#/contracts');
    const first = page.locator('.pv-contract-row').first();
    const cell = first.getByText('Đang đàm phán', {exact:true});
    // The source-status cell is in the horizontally scrollable table on mobile.
    await cell.hover();
    check(`Row hover ${width}`, await first.evaluate(e => getComputedStyle(e).backgroundColor) === 'rgb(246, 247, 252)');
    await first.locator('a').first().focus();
    await page.keyboard.press('Tab'); await page.keyboard.press('Shift+Tab');
    check(`Native contract keyboard focus ${width}`, await first.locator('a').first().evaluate(e => e.matches(':focus-visible')));
    await cell.click();
    await page.getByRole('heading', {name:'Triển khai nền tảng quản trị doanh nghiệp',exact:true}).waitFor();
    check(`Whole row opens correct contract ${width}`, page.url().endsWith('/contracts/CON-004') && await page.getByRole('dialog').count() === 0);
    await page.goBack(); await page.getByRole('heading', {name:'Hợp đồng',exact:true}).waitFor();
    await page.getByRole('textbox', {name:'Tìm hợp đồng'}).fill('Minh Hải');
    check(`Contract search ${width}`, await page.locator('.pv-contract-row').count() === 1);
    await page.getByRole('textbox', {name:'Tìm hợp đồng'}).fill('');
    await page.getByRole('combobox', {name:'Lọc trạng thái hợp đồng'}).selectOption('FAILED_SAFE');
    check(`Workflow filter ${width}`, await page.locator('.pv-contract-row').count() === 1 && await page.getByText('CON-005', {exact:true}).count() === 1);
    check(`No document overflow ${width}`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.goto(base + '#/company');
    await page.locator('.recharts-cartesian-axis-tick-value').first().waitFor();
    const chartGroups = await page.locator('.pv-two-up .pv-chart-meta').evaluateAll(es => es.map(e => e.getBoundingClientRect().top));
    if (width > 390) check(`Chart alignment ${width}`, Math.abs(chartGroups[0]-chartGroups[1]) < 1);
    report.measurements.push({width, chartGroups});
  }
  check('No runtime errors or API requests', !report.errors.length && !report.apiRequests.length);
  await page.setViewportSize({width:1440,height:1080}); await page.goto(base + '#/dashboard');
  return report;
}
