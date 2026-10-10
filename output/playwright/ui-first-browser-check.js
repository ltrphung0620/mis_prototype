async (page) => {
  const base = 'http://127.0.0.1:5173/dashboard-assets/?preview=1';
  const out = 'D:/UIT/Project/AISC2026/mis_prototype/output/playwright';
  const report = {screens:[], errors:[], apiRequests:[], checks:[]};
  page.on('pageerror', e => report.errors.push(e.message));
  page.on('request', r => { if(new URL(r.url()).pathname.startsWith('/api/')) report.apiRequests.push(r.url()); });
  for(const width of [1440,1920,390]) {
    await page.setViewportSize({width,height:width===390?844:1080});
    for(const [name,hash] of [['dashboard','/dashboard'],['company','/company'],['contracts','/contracts'],['decision','/contracts/CON-004']]) {
      await page.goto(base+'#'+hash);
      await page.locator('.pv-main h1').waitFor();
      await page.evaluate(()=>document.fonts.ready);
      await page.screenshot({path:`${out}/ui-first-${name}-${width}.png`,fullPage:true,scale:'css'});
      report.screens.push({name,width,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),height:await page.evaluate(()=>document.documentElement.scrollHeight)});
    }
  }
  await page.setViewportSize({width:1440,height:1080});
  await page.goto(base+'#/dashboard');
  await page.locator('.pv-main h1').waitFor();
  report.measurements=await page.evaluate(()=>Array.from(document.querySelectorAll('.pv-action-row,.pv-attention-list>a,.pv-chart,.pv-dashboard-top')).map(e=>({class:e.className,height:e.getBoundingClientRect().height,padding:getComputedStyle(e).padding,margin:getComputedStyle(e).margin})));
  return report;
}
