import { test, expect, type Page } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import { readFile } from 'node:fs/promises';

const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));
const detail = (page: Page) => page.getByRole('region', { name: '선택한 작업 상세' });
async function submit(page: Page) {
  const created = page.waitForResponse(r => r.url().endsWith('/api/v1/jobs') && r.request().method() === 'POST');
  await page.getByRole('button', { name: '하나의 PDF로 변환', exact: true }).click();
  const response = await created;
  expect(response.status()).toBe(202);
  return (await response.json()).jobId as string;
}
async function success(page: Page) {
  await expect(detail(page).getByText('변환 완료', { exact: true })).toBeVisible();
  await expect(detail(page).getByRole('progressbar')).toHaveAttribute('value', '100');
}
async function preview(page: Page) {
  await page.getByRole('button', { name: '결과 미리보기', exact: true }).click();
  await expect(page.getByRole('img', { name: 'PDF 1페이지 미리보기', exact: true })).toBeVisible();
  await expect(page.locator('.preview-canvas')).toHaveAttribute('aria-busy', 'false');
}
async function pageColor(page: Page, dominant: number) {
  await expect(page.locator('.preview-canvas')).toHaveAttribute('aria-busy', 'false');
  const rgb = await page.locator('.preview-canvas canvas').evaluate(element => {
    const canvas = element as HTMLCanvasElement;
    return Array.from(canvas.getContext('2d')!.getImageData(Math.floor(canvas.width / 2), Math.floor(canvas.height / 2), 1, 1).data).slice(0, 3);
  });
  expect(rgb[dominant]).toBeGreaterThan(100);
  rgb.forEach((value, index) => { if (index !== dominant) expect(value).toBeLessThan(30); });
}

test.beforeEach(async ({ page }) => { await page.goto('/'); });

test('real upload, order, TIFF, PDF render/download, history and workspace isolation', async ({ page, browser }) => {
  await page.locator('input[type=file]').setInputFiles([fixture('pages.tiff'), fixture('cover.png')]);
  await page.getByRole('button', { name: 'cover.png 위로', exact: true }).click();
  await expect(page.locator('.file-selection li').first()).toContainText('cover.png');
  await page.getByRole('combobox', { name: '페이지 크기', exact: true }).selectOption('A4');
  await page.getByRole('combobox', { name: '방향', exact: true }).selectOption('landscape');
  await page.getByRole('spinbutton', { name: '여백 (mm)' }).fill('10');
  const id = await submit(page);
  await success(page);
  await preview(page);
  await pageColor(page, 0);
  await expect(page.getByText('1 / 3 페이지', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '이전 페이지', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '다음 페이지', exact: true }).click();
  await expect(page.getByRole('img', { name: 'PDF 2페이지 미리보기', exact: true })).toBeVisible();
  await expect(page.locator('.preview-canvas')).toHaveAttribute('aria-busy', 'false');
  await pageColor(page, 1);
  await page.getByRole('button', { name: '다음 페이지', exact: true }).click();
  await expect(page.getByRole('img', { name: 'PDF 3페이지 미리보기', exact: true })).toBeVisible();
  await pageColor(page, 2);
  await expect(page.getByRole('button', { name: '다음 페이지', exact: true })).toBeDisabled();
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: /PDF 다운로드/ }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe(`convertflow-${id}.pdf`);
  const path = await download.path();
  expect(path).toBeTruthy();
  expect((await readFile(path!)).subarray(0, 5).toString()).toBe('%PDF-');
  // Fresh context has no workspace cookie or per-job token.
  const outsider = await browser.newContext();
  try {
    const response = await outsider.request.get(new URL(`/api/v1/jobs/${id}/download`, page.url()).href);
    expect(response.status()).toBe(404);
  } finally { await outsider.close(); }
  if (await page.getByRole('combobox', { name: '화면 선택' }).isVisible()) {
    await page.getByRole('combobox', { name: '화면 선택' }).selectOption('history');
  } else { await page.getByRole('navigation', { name: '주 메뉴' }).getByRole('button', { name: /작업 이력/ }).click(); }
  await page.getByPlaceholder('파일명 또는 Job ID').fill(id);
  await expect(page.getByText('총 1건', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('empty file rejected locally and disguised PNG rejected by real API', async ({ page }) => {
  await page.locator('input[type=file]').setInputFiles({ name: 'empty.png', mimeType: 'image/png', buffer: Buffer.alloc(0) });
  await expect(page.getByRole('button', { name: '하나의 PDF로 변환', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '오류 파일 1개 제거', exact: true }).click();
  await page.locator('input[type=file]').setInputFiles({ name: 'fake.png', mimeType: 'image/png', buffer: Buffer.from('not an image') });
  const response = page.waitForResponse(r => r.url().endsWith('/api/v1/jobs') && r.request().method() === 'POST');
  await page.getByRole('button', { name: '하나의 PDF로 변환', exact: true }).click();
  expect((await response).status()).toBe(422);
  await expect(page.locator('.global-notice')).toBeVisible();
  await expect(detail(page).getByRole('button', { name: /PDF 다운로드/ })).toHaveCount(0);
});

test('real conversion failure preserves Attempt and does not publish PDF', async ({ page }) => {
  await page.locator('input[type=file]').setInputFiles(fixture('cover.png'));
  await page.getByRole('spinbutton', { name: '여백 (mm)' }).fill('50');
  await submit(page);
  await expect(detail(page).getByText('실패', { exact: true })).toBeVisible();
  await expect(page.locator('.attempt-list')).toContainText('시도 #1');
  await expect(page.locator('.attempt-list .attempt-error')).toBeVisible();
  await expect(detail(page).getByRole('button', { name: /PDF 다운로드/ })).toHaveCount(0);
  await expect(detail(page).getByRole('progressbar')).not.toHaveAttribute('value', '100');
});

test('preview network failure recovers and theme survives reload', async ({ page }) => {
  await page.locator('input[type=file]').setInputFiles(fixture('cover.png'));
  await submit(page);
  await success(page);
  await page.route('**/api/v1/jobs/*/download', route => route.abort('failed'));
  await page.getByRole('button', { name: '결과 미리보기', exact: true }).click();
  await expect(page.getByRole('button', { name: '미리보기 다시 불러오기', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: /PDF 다운로드/ })).toBeEnabled();
  await page.unroute('**/api/v1/jobs/*/download');
  await page.getByRole('button', { name: '미리보기 다시 불러오기', exact: true }).click();
  await expect(page.getByRole('img', { name: 'PDF 1페이지 미리보기', exact: true })).toBeVisible();
  await expect(page.locator('.preview-canvas')).toHaveAttribute('aria-busy', 'false');
  const themeButton = page.getByRole('button', { name: /^(밝은 테마|어두운 테마)$/ });
  const oldLabel = await themeButton.getAttribute('aria-label');
  await themeButton.click();
  await page.reload();
  await expect(page.getByRole('button', { name: oldLabel === '밝은 테마' ? '어두운 테마' : '밝은 테마', exact: true })).toBeVisible();
  await success(page);
});

test('@queued cancellation before claim has no Attempt or PDF', async ({ page }) => {
  // Run only while the harness has stopped Worker; never fake job responses.
  await page.locator('input[type=file]').setInputFiles(fixture('cover.png'));
  await submit(page);
  await expect(detail(page).locator('.badge.QUEUED')).toHaveText('대기 중');
  await page.getByRole('button', { name: '작업 취소', exact: true }).click();
  await expect(detail(page).getByText('취소됨', { exact: true })).toBeVisible();
  await expect(detail(page).getByRole('progressbar')).toHaveAttribute('value', '0');
  await expect(page.getByText('Worker가 실행하기 전입니다.', { exact: false })).toBeVisible();
  await expect(page.locator('.attempt-list li')).toHaveCount(0);
  await expect(detail(page).getByRole('button', { name: /PDF 다운로드/ })).toHaveCount(0);
});
