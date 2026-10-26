import { describe, expect, it } from 'vitest';
import { terminal } from './api';
describe('polling lifecycle', () => {
  it('stops only for terminal jobs', () => {
    expect(terminal('SUCCESS')).toBe(true);
    expect(terminal('FAILED')).toBe(true);
    expect(terminal('QUEUED')).toBe(false);
    expect(terminal('PROCESSING')).toBe(false);
    expect(terminal()).toBe(false);
  });
});
