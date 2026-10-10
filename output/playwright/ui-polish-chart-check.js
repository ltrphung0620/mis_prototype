async (page) => {
 const base='http://127.0.0.1:5173/dashboard-assets/?preview=1';
 const checks=[];const apiRequests=[];
 page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/'))apiRequests.push(r.url());});
 const check=(name,ok)=>{if(!ok)throw new Error(name);checks.push(name);};
 await page.setViewportSize({width:1440,height:1080});
 await page.goto(base+'#/dashboard');await page.locator('.pv-main h1').waitFor();
 await page.getByRole('application').focus();await page.keyboard.press('ArrowRight');
 check('Keyboard chart tooltip',await page.locator('.recharts-tooltip-wrapper').innerText().then(t=>t.includes('Dữ liệu minh họa')&&t.includes('VND')));
 await page.getByRole('button',{name:'Thu dự kiến',exact:true}).click();check('Legend series toggle',await page.getByRole('button',{name:'Thu dự kiến',exact:true}).getAttribute('aria-pressed')==='false');
 await page.goto(base+'#/company?section=business');await page.locator('.pv-main h1').waitFor();
 await page.getByRole('button',{name:/^Đang triển khai/}).click();
 await page.getByRole('table').getByText('ORD-001',{exact:true}).waitFor({state:'hidden'}); const orderTable=page.getByRole('table');check('Donut legend filters orders',await orderTable.getByText('ORD-002',{exact:true}).count()===1 && await orderTable.getByText('ORD-001',{exact:true}).count()===0);
 await page.locator('.recharts-bar-rectangle').first().click();
 await page.getByRole('heading',{name:'Triển khai nền tảng quản trị doanh nghiệp'}).waitFor();check('Contract bar chart drill-down',page.url().includes('CON-004'));
 await page.goto(base+'#/contracts/CON-002');await page.locator('.pv-main h1').waitFor();await page.getByRole('button',{name:'Xem yêu cầu bổ sung'}).click();
 const dialog=page.getByRole('dialog');await dialog.getByRole('button',{name:'Kiểm tra form minh họa'}).click();check('Demo form invalid state',await dialog.getByRole('alert').innerText().then(t=>t.includes('lớn hơn 0')));
 await dialog.getByRole('spinbutton',{name:'Số tiền yêu cầu (VND)'}).fill('1000000');await dialog.getByRole('button',{name:'Kiểm tra form minh họa'}).click();check('Demo form local-only success',await dialog.getByRole('status').innerText().then(t=>t.includes('không resume workflow')));await page.keyboard.press('Escape');
 await page.setViewportSize({width:768,height:1024});await page.goto(base+'#/company?section=invoices');await page.locator('.pv-main h1').waitFor();check('768px has no overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.setViewportSize({width:720,height:540});await page.goto(base+'#/dashboard');await page.locator('.pv-main h1').waitFor();check('Layout at 200% equivalent CSS viewport',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.emulateMedia({reducedMotion:'reduce'});await page.getByRole('combobox',{name:'Trạng thái preview'}).selectOption('loading');check('Reduced motion disables skeleton animation',await page.locator('.pv-loading>div').first().evaluate(e=>getComputedStyle(e).animationName)==='none');
 await page.getByRole('combobox',{name:'Trạng thái preview'}).selectOption('ready');await page.emulateMedia({reducedMotion:'no-preference'});await page.setViewportSize({width:1440,height:1080});
 await page.goto(base+'#/dashboard');await page.locator('.pv-main h1').waitFor();
 check('No backend requests',apiRequests.length===0);
 return {checks,apiRequests};
}
