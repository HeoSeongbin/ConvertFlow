import { useQuery } from '@tanstack/react-query';
import { Activity, RefreshCw, Server, Timer, CheckCircle2 } from 'lucide-react';
import { api, errorMessage } from '../../services/api';

export interface DashboardData {
  sampledAt: string; windowStart: string; windowMinutes: number; total: number;
  counts: Record<string, number>; recentSuccess: number; recentFailedAttempts: number;
  recentSuccessfulAttempts: number; processingSamples: number; throughputJobsPerMinute: number;
  meanProcessingSeconds: number | null; maxProcessingSeconds: number | null;
  meanEndToEndSeconds: number | null; pendingDispatch: number; errors: { code: string; count: number }[];
}
export interface WorkersData {
  sampledAt: string; workersSampledAt: string | null; workersError: string | null; totalKnown: number;
  staleAfterSeconds: number; items: { name: string; status: 'ONLINE' | 'UNKNOWN'; lastSeenAt: string;
    lastProbeAt: string; concurrency: number | null; activeCount: number | null; recentSuccess: number;
    recentFailedAttempts: number; jobs: { jobId: string; status: string; heartbeatAt: string | null; leaseExpiresAt: string | null }[] }[];
  queue: { name: string; scope: string; status: 'KNOWN' | 'UNKNOWN'; sampledAt: string | null; readyMessages: number | null; error: string | null };
}
export const seconds = (value: number | null) => value === null ? '—' : `${value.toFixed(2)}초`;
export const count = (value: number | null) => value === null ? 'UNKNOWN' : value.toLocaleString('ko-KR');
export function displayObservation(data: WorkersData | undefined, failed = false, instant = Date.now()): WorkersData | undefined {
  if (!data) return undefined;
  const fresh = (value: string | null) => {
    const age = value ? instant - Date.parse(value) : NaN;
    return Number.isFinite(age) && age >= -5000 && age <= data.staleAfterSeconds * 1000;
  };
  const workerKnown = !failed && fresh(data.workersSampledAt);
  const queueKnown = !failed && fresh(data.queue.sampledAt);
  return { ...data, workersError: failed ? 'API_UNAVAILABLE' : data.workersError ?? (workerKnown ? null : 'STALE_OBSERVATION'),
    items: data.items.map(worker => workerKnown && fresh(worker.lastSeenAt) ? worker : { ...worker, status: 'UNKNOWN', concurrency: null, activeCount: null, jobs: [] }),
    queue: queueKnown ? data.queue : { ...data.queue, status: 'UNKNOWN', readyMessages: null, error: failed ? 'API_UNAVAILABLE' : 'STALE_OBSERVATION' } };
}
const time = (value: string | null) => value ? new Date(value).toLocaleString('ko-KR') : '아직 수집하지 않음';
const statusLabels: Record<string, string> = { QUEUED: '대기', PROCESSING: '변환 중', RETRY_WAIT: '재시도 대기', CANCEL_REQUESTED: '취소 요청', SUCCESS: '성공', FAILED: '실패', CANCELLED: '취소' };

export default function Monitoring({ mode, selectJob }: { mode: 'dashboard' | 'workers'; selectJob: (jobId: string) => void }) {
  const dashboard = useQuery({ queryKey: ['monitoring', 'dashboard'], queryFn: async () => (await api.get<DashboardData>('/monitoring/dashboard')).data, refetchInterval: 5000 });
  const workers = useQuery({ queryKey: ['monitoring', 'workers'], queryFn: async () => (await api.get<WorkersData>('/monitoring/workers')).data, refetchInterval: 5000 });
  const refreshing = dashboard.isFetching || workers.isFetching;
  const data = dashboard.data;
  const observed = displayObservation(workers.data, workers.isError);
  return <div className="monitoring">
    <div className="monitor-toolbar"><p>작업 통계는 이 브라우저 작업공간 기준 · 최근 통계는 60분</p><button className="text-button" disabled={refreshing} onClick={() => { void dashboard.refetch(); void workers.refetch(); }}><RefreshCw size={13} className={refreshing ? 'spin' : ''}/> 새로 조회</button></div>
    {dashboard.isError && <div className="error" role="alert">작업 통계: {errorMessage(dashboard.error)}</div>}
    {workers.isError && <div className="error" role="alert">Worker 관측: {errorMessage(workers.error)}</div>}
    {dashboard.isPending && <p role="status">작업 통계를 불러오는 중…</p>}
    {mode === 'dashboard' && data && <>
      <div className="metric-grid">
        <article className="panel metric"><Activity size={19}/><span>전체 작업</span><strong>{count(data.total)}</strong><small>성공 {count(data.counts.SUCCESS ?? 0)} · 실패 {count(data.counts.FAILED ?? 0)}</small></article>
        <article className="panel metric"><CheckCircle2 size={19}/><span>최근 60분 완료</span><strong>{count(data.recentSuccess)}</strong><small>성공 처리량 {data.throughputJobsPerMinute.toFixed(2)} Job/분</small></article>
        <article className="panel metric"><Timer size={19}/><span>성공 실행 평균</span><strong>{seconds(data.meanProcessingSeconds)}</strong><small>시작→완료 · 표본 {count(data.processingSamples)}개</small></article>
        <article className="panel metric"><Server size={19}/><span>최근 실패 Attempt</span><strong>{count(data.recentFailedAttempts)}</strong><small>재시도 후 성공한 오류도 포함</small></article>
      </div>
      <div className="monitor-grid"><section className="panel"><div className="panel-heading"><h2>작업 상태 분포</h2><span className="muted">전체 이력</span></div><div className="status-bars">{Object.entries(statusLabels).map(([status, label]) => <div key={status}><span>{label}</span><progress aria-label={label} max={Math.max(1, data.total)} value={data.counts[status] ?? 0}/><strong>{count(data.counts[status] ?? 0)}</strong></div>)}</div>{data.total === 0 && <p className="monitor-note">등록한 작업이 없습니다. 이미지를 변환하면 통계가 표시됩니다.</p>}</section>
      <section className="panel"><div className="panel-heading"><h2>처리시간 · 오류</h2><span className="muted">최근 60분</span></div><dl className="monitor-stats"><dt>성공 실행 최대</dt><dd>{seconds(data.maxProcessingSeconds)}</dd><dt>접수→성공 평균</dt><dd>{seconds(data.meanEndToEndSeconds)}</dd><dt>미발행 예약 / 대기</dt><dd>{count(data.pendingDispatch)}</dd></dl><p className="monitor-note">실행 시간은 마지막 성공 Attempt 기준입니다. 접수→성공 시간은 대기와 재시도도 포함합니다.</p><h3>실패 코드 상위 10개</h3>{data.errors.length ? <ul className="error-counts">{data.errors.map(error => <li key={error.code}><code>{error.code}</code><strong>{error.count}회</strong></li>)}</ul> : <p className="monitor-note">이 시간대에 기록된 실패 Attempt가 없습니다.</p>}</section></div>
    </>}
    {workers.isPending && <p role="status">Worker 관측을 불러오는 중…</p>}
    {observed && <>
      <section className="panel queue-panel"><div><span className="small-label">BROKER QUEUE · 전체 인프라</span><h2>{observed.queue.name} 대기 메시지 <strong>{count(observed.queue.readyMessages)}</strong></h2><p>브로커에서 아직 가져가지 않은 메시지입니다. 실행·예약·중복 전달 때문에 Job 수와 다를 수 있습니다.</p></div><div><span className={`badge ${observed.queue.status}`}>{observed.queue.status === 'KNOWN' ? '관측됨' : 'UNKNOWN'}</span><small>큐 관측 {time(observed.queue.sampledAt)}</small></div></section>
      <section className="panel worker-panel"><div className="panel-heading"><h2>Worker Monitoring</h2><span className="muted">알려진 {observed.totalKnown}개 · 최대 100개 표시</span></div>
        {observed.workersError && <p className="monitor-warning" role="status">응답이 없거나 관측이 오래되었습니다. UNKNOWN은 Worker 종료를 뜻하지 않습니다.</p>}
        {!observed.items.length ? <div className="history-empty">아직 응답이 확인된 Worker가 없습니다. Observer의 다음 수집을 기다려 주세요.</div> : <div className="table-scroll"><table><thead><tr><th>Worker / 마지막 응답</th><th>관측 상태</th><th>동시 실행 슬롯 / 활성 Task</th><th>내 작업공간 실행 작업</th><th>내 최근 성공 / 실패 Attempt</th></tr></thead><tbody>{observed.items.map(worker => <tr key={worker.name}><td><strong>{worker.name}</strong><small>{time(worker.lastSeenAt)}</small></td><td><span className={`badge ${worker.status}`}>{worker.status}</span></td><td>{count(worker.concurrency)} / {count(worker.activeCount)}</td><td>{worker.jobs.length ? worker.jobs.map(job => <div key={job.jobId}><button className="job-link" onClick={() => selectJob(job.jobId)}>{job.jobId.slice(0, 8)} · {job.status}</button><small>Heartbeat {time(job.heartbeatAt)}</small></div>) : worker.status === 'UNKNOWN' || worker.activeCount === null ? 'UNKNOWN' : '표시할 내 작업 없음'}</td><td>{worker.recentSuccess} / {worker.recentFailedAttempts}</td></tr>)}</tbody></table></div>}
        <p className="monitor-note">Worker 관측 {time(observed.workersSampledAt)} · {observed.staleAfterSeconds}초가 지나면 UNKNOWN · 다른 작업공간의 Job ID는 표시하지 않습니다.</p>
      </section>
    </>}
    {data && <p className="monitor-note">DB 통계 조회 {time(data.sampledAt)} · 관측치는 서로 다른 시점에 수집됩니다.</p>}
  </div>;
}
