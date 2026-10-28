import { describe, expect, it } from 'vitest';
import { previewGeometry, errorHint, progressNote, durationLabel } from './presentation';
describe('preview resource bounds', () => {
  it('caps native canvas pixel count on huge portrait pages and dense screens', () => {
    const geometry = previewGeometry(10000, 20000, 1500, 4);
    expect(10000 * geometry.scale * 20000 * geometry.scale).toBeLessThanOrEqual(2_000_001);
    expect(geometry.cssWidth).toBeLessThanOrEqual(1200);
  });
  it('fits a page to a narrow mobile container without altering its ratio', () => {
    const geometry = previewGeometry(612, 792, 280, 1);
    expect(geometry.cssWidth).toBeCloseTo(280);
    expect(geometry.cssHeight / geometry.cssWidth).toBeCloseTo(792 / 612);
  });
});
describe('actual execution guidance', () => {
  it('does not display an unstarted cancellation as unfinished running work', () => {
    expect(durationLabel({ status: 'CANCELLED', startedAt: null, durationSeconds: null })).toBe('실행 안 함');
    expect(durationLabel({ status: 'PROCESSING', startedAt: '2026-10-28', durationSeconds: null })).toBe('실행 중');
    expect(durationLabel({ status: 'SUCCESS', startedAt: null, durationSeconds: null })).toBe('시간 기록 없음');
  });
  it('does not describe retry reservation or cancellation as successful conversion', () => {
    expect(progressNote('RETRY_WAIT')).toContain('아직 다음 실행을 시작하지');
    expect(progressNote('CANCELLED')).toContain('마지막 실제 처리');
    expect(progressNote('CANCEL_REQUESTED')).toContain('다음 처리 경계');
  });
  it('gives actionable input and storage error guidance', () => {
    expect(errorHint('INVALID_OPTIONS')).toContain('여백');
    expect(errorHint('SOURCE_MISSING')).toContain('다시 선택');
    expect(errorHint('STORAGE_ERROR')).toContain('권한');
  });
});
