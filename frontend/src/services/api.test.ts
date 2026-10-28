import { describe, expect, it } from 'vitest';
import { terminal, errorMessage } from './api';
describe('polling lifecycle', () => {
  it('preserves structured errors when the PDF request expects binary data', () => {
    const data = new TextEncoder().encode(JSON.stringify({ detail: { code: 'MISSING_RESULT', message: '결과 파일을 찾을 수 없습니다.' } })).buffer;
    expect(errorMessage({ isAxiosError: true, response: { data } })).toBe('결과 파일을 찾을 수 없습니다.');
    expect(() => errorMessage({ isAxiosError: true, response: { data: new ArrayBuffer(3) } })).not.toThrow();
  });
  it('stops only for terminal jobs', () => {
    expect(terminal('SUCCESS')).toBe(true);
    expect(terminal('FAILED')).toBe(true);
    expect(terminal('CANCELLED')).toBe(true);
    expect(terminal('RETRY_WAIT')).toBe(false);
    expect(terminal('CANCEL_REQUESTED')).toBe(false);
    expect(terminal('QUEUED')).toBe(false);
    expect(terminal('PROCESSING')).toBe(false);
    expect(terminal()).toBe(false);
  });
});
