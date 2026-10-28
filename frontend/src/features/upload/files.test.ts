import { describe, expect, it } from 'vitest';
import { fileError, moveEntry, uploadError } from './files';
describe('ordered upload', () => {
  it('rejects an empty image before starting upload', () => { expect(fileError({ name: 'empty.png', size: 0 })).toContain('빈 파일'); });
  it('moves without mutating and preserves all entries', () => { const a = ['A', 'B', 'C']; expect(moveEntry(a, 1, -1)).toEqual(['B', 'A', 'C']); expect(moveEntry(a, 1, 1)).toEqual(['A', 'C', 'B']); expect(a).toEqual(['A', 'B', 'C']); expect(moveEntry(a, 0, -1)).toBe(a); });
  it('validates each file', () => { expect(fileError({ name: 'a.PNG', size: 10 })).toBeUndefined(); expect(fileError({ name: 'a.exe', size: 10 })).toBeDefined(); expect(fileError({ name: 'a.png', size: 21 * 1024 * 1024 })).toBeDefined(); });
  it('validates aggregate limits', () => { const entry = { id: 'a', file: { size: 6 * 1024 * 1024 } as File }; expect(uploadError(Array(21).fill(entry))).toBeDefined(); expect(uploadError(Array(20).fill(entry))).toContain('100 MiB'); expect(uploadError([{ ...entry, error: 'invalid' }])).toBeDefined(); });
});
