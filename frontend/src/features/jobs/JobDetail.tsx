import { lazy, Suspense, useState } from 'react';
import { Check, Download, FileText, Eye, RotateCcw } from 'lucide-react';
import { type Job, type JobReference, errorMessage } from '../../services/api';
import { PREVIEW_LIMIT, errorHint, progressNote } from './presentation';
import PreviewBoundary from './PreviewBoundary';
const PDFPreview = lazy(() => import('./PDFPreview'));
const labels = { QUEUED: '대기 중', PROCESSING: '변환 중', SUCCESS: '변환 완료', FAILED: '실패', RETRY_WAIT: '재시도 대기', CANCEL_REQUESTED: '취소 요청', CANCELLED: '취소됨' };
const stages: Record<string, string> = { QUEUED: 'Worker 대기', INPUT_VALIDATION: '입력 검증', PAGE_PROCESSING: '페이지 변환', RESULT_VALIDATION: '결과 검증', SUCCESS: '게시 완료', FAILED: '변환 실패', RETRY_WAIT: '재시도 예약', CANCEL_REQUESTED: '취소 확인 중', CANCELLED: '취소 완료' };
const date = (value: string) => new Date(value).toLocaleString('ko-KR');
export default function JobDetail({ job, reference, pending, error, refresh, download, downloading, act, actionPending }: { job?: Job; reference: JobReference | null; pending: boolean; error: unknown; refresh: () => void; download: () => void; downloading: boolean; act: (action: 'retry' | 'cancel') => void; actionPending: boolean }) {
  const [preview, setPreview] = useState(false);
  return <section id="job-detail" className="panel status-panel" tabIndex={-1} aria-label="선택한 작업 상세"><div className="panel-heading"><div><span className="step">02</span><h2>작업 상세</h2></div><span className="live-label">DB 기준 처리 상태</span></div>
    {!reference ? <div className="status-empty"><div className="document-art"><FileText size={44}/><span><Check size={14}/></span></div><h3>다음 문서를 기다리고 있어요</h3><p>파일을 업로드하거나 작업 이력에서<br/>조회할 작업을 선택하세요.</p></div> : pending ? <p role="status">작업 상태를 불러오는 중…</p> : error ? <div role="alert" className="error">{errorMessage(error)}<button className="text-button" onClick={refresh}>다시 조회</button></div> : job && <div className="job-content">
      <span className={`badge ${job.status}`}>{labels[job.status]}</span><h3>{job.filename}{job.totalFiles > 1 && ` 외 ${job.totalFiles - 1}개`}</h3><code className="job-id">{job.jobId}</code>
      <div className="progress-label"><span>{stages[job.stage] ?? job.stage}</span><strong>{job.progress}%</strong></div><progress aria-label="변환 진행률" value={job.progress} max={100}/><p className="progress-note" role="status">{progressNote(job.status)}</p>
      <div className="processing-counters"><span><strong>{job.processedFiles}/{job.totalFiles}</strong> 파일</span><span><strong>{job.processedPages}/{job.totalPages}</strong> 페이지</span>{job.durationSeconds !== null && <span><strong>{job.durationSeconds.toFixed(2)}초</strong> 실행 시간</span>}</div>
      {job.nextRetryAt && <p className="retry-note">자동 재시도 예약: {date(job.nextRetryAt)}</p>}
      <div className="job-actions">{job.canRetry && <button className="primary" disabled={actionPending} onClick={() => act('retry')}><RotateCcw size={16}/>같은 파일로 재시도</button>}{job.canCancel && <button className="text-button cancel-button" disabled={actionPending} onClick={() => act('cancel')}>작업 취소</button>}</div>
      {job.errorCode && <div className="error" role="alert"><strong>{job.errorCode}</strong><p>{job.errorMessage}</p><p>{errorHint(job.errorCode)}</p></div>}
      {job.status === 'FAILED' && !job.canRetry && <p className="progress-note">{job.retryBlockedReason ?? '입력과 옵션을 확인한 뒤 새 작업을 등록하세요.'}</p>}
      {job.downloadAvailable && <div className="result-actions"><button className="primary" disabled={downloading} onClick={download}><Download size={17}/>{downloading ? '다운로드 중…' : `PDF 다운로드 · ${job.result?.pageCount ?? job.totalPages}페이지`}</button>{job.result && job.result.fileSize <= PREVIEW_LIMIT ? <button className="text-button" aria-expanded={preview} onClick={() => setPreview(value => !value)}><Eye size={16}/>{preview ? '미리보기 닫기' : '결과 미리보기'}</button> : <p className="monitor-note">파일 크기 정보가 없거나 32 MiB를 넘는 PDF는 다운로드해서 확인하세요.</p>}</div>}
      {preview && job.downloadAvailable && <PreviewBoundary><Suspense fallback={<p role="status">PDF 뷰어를 준비하는 중…</p>}><PDFPreview reference={reference}/></Suspense></PreviewBoundary>}
      <details className="job-details"><summary>입력 파일 · 변환 설정 · 실행 정보</summary><dl className="job-meta"><dt>처리 시도</dt><dd>{job.attemptCount}회 · 세대 {job.runGeneration}</dd><dt>등록</dt><dd>{date(job.createdAt)}</dd><dt>시작</dt><dd>{job.startedAt ? date(job.startedAt) : job.status === 'CANCELLED' ? '실행 안 함' : '대기 중'}</dd><dt>완료</dt><dd>{job.completedAt ? date(job.completedAt) : '—'}</dd><dt>출력 설정</dt><dd>{job.options && `${job.options.pageSize} / ${job.options.orientation} / 여백 ${job.options.marginMm}mm / ${job.options.fit} / 품질 ${job.options.quality}`}</dd>{job.result && <><dt>결과 크기</dt><dd>{(job.result.fileSize / 1024 / 1024).toFixed(2)} MiB</dd></>}</dl><ol className="detail-files">{job.files?.map(file => <li key={file.fileId}><strong>{file.filename}</strong><small>{file.pageCount}페이지 · {(file.fileSize / 1024 / 1024).toFixed(2)} MiB</small></li>)}</ol></details>
    </div>}
    <div className="status-foot"><span className="dot"/> 파일 전송과 Worker의 변환 진행률을 구분해 표시합니다.</div></section>;
}
