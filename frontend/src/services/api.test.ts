import { describe, expect, it } from 'vitest';
import { terminal } from './api';
describe('polling lifecycle', () => {
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
