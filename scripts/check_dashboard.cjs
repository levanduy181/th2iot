const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const path = require('path');
const fs = require('fs');
(async () => {
  const root = path.resolve(__dirname, '..');
  fs.mkdirSync(path.join(root,'output/qa'), {recursive:true});
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROME_PATH});
  const page = await browser.newPage({viewport:{width:1440, height:1100}, deviceScaleFactor:1});
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('http://127.0.0.1:8502', {waitUntil:'domcontentloaded'});
  await page.getByText('Bản ghi trong khoảng', {exact:true}).waitFor({timeout:60000});
  await page.locator('.js-plotly-plot').first().waitFor({timeout:30000});
  await page.screenshot({path:path.join(root,'output/dashboard.png'),fullPage:true});
  await page.getByRole('tab', {name:'Sau xử lý', exact:true}).click();
  await page.getByText('Chuẩn hóa 0–1', {exact:true}).first().waitFor({timeout:30000});
  await page.screenshot({path:path.join(root,'output/dashboard_processed.png'),fullPage:true});
  await page.getByRole('tab', {name:'Chất lượng', exact:true}).click();
  await page.getByText('Sequence thiếu giữa các bản tin', {exact:true}).waitFor();
  await page.getByRole('tab', {name:'Bảng dữ liệu', exact:true}).click();
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', {name:/Tải CSV dữ liệu gốc/}).click()
  ]);
  await download.saveAs(path.join(root,'output/qa/download.csv'));
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('tab', {name:'Theo thời gian', exact:true}).click();
  await page.screenshot({path:path.join(root,'output/qa/mobile.png'),fullPage:true});
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2);
  const streamlitErrors = await page.locator('[data-testid="stException"]').count();
  if (errors.length || streamlitErrors || overflow) throw new Error(JSON.stringify({errors,streamlitErrors,overflow}));
  fs.writeFileSync(path.join(root,'output/qa/browser-check.json'),JSON.stringify({errors,streamlitErrors,overflow,download:download.suggestedFilename()},null,2));
  await browser.close();
  console.log('Desktop, mobile, tabs and CSV download passed');
})().catch(e=>{console.error(e);process.exit(1)});
