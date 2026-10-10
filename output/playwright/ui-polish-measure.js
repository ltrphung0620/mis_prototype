async (page) => {
  const report = { measurements: [] };
  for (const name of ['dashboard', 'company', 'contracts']) {
    await page.setViewportSize({ width: 1440, height: 1080 });
    await page.goto('http://127.0.0.1:5173/dashboard-assets/?preview=1#/' + name);
    await page.locator('.pv-main h1').waitFor();
    await page.evaluate(() => document.fonts.ready); if (name !== 'contracts') await page.locator('.recharts-cartesian-axis-tick-value').first().waitFor();
    report.measurements.push(await page.evaluate((name) => {
      const rgb = s => (s.match(/[\d.]+/g) || []).map(Number);
      const luminance = s => rgb(s).slice(0, 3).map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((n, v, i) => n + v * [.2126, .7152, .0722][i], 0);
      const selectors = ['.pv-main h1', '.pv-section h2', '.pv-action-row h3', '.pv-action-row p', '.pv-badge', '.pv-kpi-strip dt', '.pv-kpi-strip dd', '.pv-source', '.pv-snapshot-context', 'th', 'td', '.pv-contract-link strong', '.pv-search input', '.recharts-cartesian-axis-tick-value', '.pv-legend button', '.pv-button--primary'];
      const styles = selectors.flatMap(selector => {
        const e = document.querySelector(selector); if (!e) return [];
        const s = getComputedStyle(e);
        let bg = 'rgb(255, 255, 255)', parent = e;
        while (parent) {
          const c = getComputedStyle(parent).backgroundColor;
          if ((rgb(c)[3] ?? 1) === 1) { bg = c; break; }
          parent = parent.parentElement;
        }
        const fg = e.tagName === 'text' ? s.fill : s.color;
        const a = luminance(fg), b = luminance(bg);
        return [{selector, text: e.textContent.trim().slice(0, 60), font: s.fontFamily, size: s.fontSize, weight: s.fontWeight, lineHeight: s.lineHeight, foreground: fg, background: bg, contrast: +((Math.max(a,b)+.05)/(Math.min(a,b)+.05)).toFixed(2)}];
      });
      return { name, height: document.documentElement.scrollHeight, styles, rows: [...document.querySelectorAll('.pv-action-row, .pv-attention-list > a')].map(e => ({height: e.getBoundingClientRect().height, padding: getComputedStyle(e).padding})) };
    }, name));
  }
  return report;
}
