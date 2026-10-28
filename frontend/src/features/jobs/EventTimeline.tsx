import { useState } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { api, errorMessage, jobHeaders, terminal, type Job, type JobEvent, type JobReference } from '../../services/api';
interface EventPage { items: JobEvent[]; hasMore: boolean; nextBefore: number | null }
export default function EventTimeline({ reference, job }: { reference: JobReference; job: Job }) {
  const [problems, setProblems] = useState(false);
  const query = useInfiniteQuery({ queryKey: ['events', reference.jobId, job.runGeneration, terminal(job.status) ? job.status : 'active'], initialPageParam: null as number | null,
    queryFn: async ({pageParam}) => (await api.get<EventPage>(`/jobs/${reference.jobId}/events`, { headers: jobHeaders(reference), params: { before: pageParam ?? undefined, order: 'desc', limit: 30 } })).data,
    getNextPageParam: page => page.hasMore ? page.nextBefore ?? undefined : undefined, refetchInterval: terminal(job.status) ? false : 1500 });
  const all = query.data?.pages.flatMap(page => page.items) ?? [];
  const visible = problems ? all.filter(event => ['FAILED', 'RECOVERY_REQUIRED', 'RETRY_SCHEDULED', 'MANUAL_RETRY_REQUESTED', 'CANCELLED', 'CANCEL_REQUESTED'].includes(event.type)) : all;
  return <section className="panel timeline-panel"><div className="panel-heading"><h2>작업 이벤트 타임라인</h2><button className="text-button" aria-pressed={problems} onClick={() => setProblems(value => !value)}>{problems ? '전체 이벤트 보기' : '오류·재시도·취소'}</button></div>
    <p className="monitor-note">최신순 · 불러온 {all.length}개 중 {visible.length}개 표시 · {job.jobId.slice(0,8)}</p>
    {query.isPending ? <p role="status">이력을 불러오는 중…</p> : query.isError ? <div role="alert" className="error">{errorMessage(query.error)}<button className="text-button" onClick={() => query.refetch()}>이력 다시 조회</button></div> : <ol className="timeline">{visible.map(event => <li key={event.eventId} className={`event-${event.type}`}><time>{new Date(event.createdAt).toLocaleString('ko-KR')}</time><span className="event-type">{event.type}</span>{event.attemptId && <code className="event-attempt">시도 {event.attemptId.slice(0,8)}</code>}<strong>{event.message}</strong>{event.details.processedPages !== undefined && <small>페이지 {event.details.processedPages}/{event.details.totalPages}</small>}</li>)}</ol>}
    {!query.isPending && !query.isError && !visible.length && <p className="monitor-note">불러온 이력에 해당 이벤트가 없습니다.</p>}
    {query.hasNextPage && <button className="text-button load-events" disabled={query.isFetching} onClick={() => query.fetchNextPage()}>{query.isFetchingNextPage ? '불러오는 중…' : '이벤트 더 보기'}</button>}
  </section>;
}
