import { describe, expect, it } from 'vitest';
import { count, seconds, displayObservation, type WorkersData } from './Monitoring';

describe('observation display', () => {
  it('keeps unknown counts distinct from measured zero', () => {
    expect(count(null)).toBe('UNKNOWN');
    expect(count(0)).toBe('0');
  });
  it('keeps missing duration distinct from an immediate success', () => {
    expect(seconds(null)).toBe('—');
    expect(seconds(0)).toBe('0.00초');
  });
  const instant = Date.parse('2026-10-28T06:00:00Z');
  const data: WorkersData = { sampledAt: new Date(instant).toISOString(), workersSampledAt: new Date(instant).toISOString(), workersError: null, totalKnown: 1, staleAfterSeconds: 30,
    items: [{ name: 'worker', status: 'ONLINE', lastSeenAt: new Date(instant).toISOString(), lastProbeAt: new Date(instant).toISOString(), concurrency: 1, activeCount: 0, recentSuccess: 0, recentFailedAttempts: 0, jobs: [] }],
    queue: { name: 'celery', scope: 'infrastructure', status: 'KNOWN', sampledAt: new Date(instant).toISOString(), readyMessages: 0, error: null } };
  it('downgrades cached values when the API can no longer confirm observations', () => {
    const observed = displayObservation(data, true, instant)!;
    expect(observed.items[0].status).toBe('UNKNOWN');
    expect(observed.items[0].activeCount).toBeNull();
    expect(observed.queue.readyMessages).toBeNull();
    expect(data.items[0].status).toBe('ONLINE');
  });
  it('expires client-side cached observations without turning measured zero into unknown early', () => {
    expect(displayObservation(data, false, instant + 29000)!.queue.readyMessages).toBe(0);
    expect(displayObservation(data, false, instant + 31000)!.queue.readyMessages).toBeNull();
    expect(displayObservation(data, false, instant + 31000)!.items[0].status).toBe('UNKNOWN');
  });
});
