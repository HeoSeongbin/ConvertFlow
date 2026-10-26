import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowDown, ArrowUp, ArrowDownToLine, ArrowRight, Check, FileImage, FileText, History, Layers3, LoaderCircle, Moon, Sun, UploadCloud, X } from 'lucide-react';
import { api, defaultOptions, errorMessage, jobHeaders, terminal, type Job, type JobEvent, type JobPage, type JobReference, type Options } from '../services/api';
import { fileError, moveEntry, uploadError, type UploadEntry } from '../features/upload/files';
const labels = { QUEUED: '대기 중', PROCESSING: '변환 중', SUCCESS: '변환 완료', FAILED: '실패' };
const stages: Record<string, string> = { QUEUED: 'Worker 대기', INPUT_VALIDATION: '입력 파일 검증', PAGE_PROCESSING: '이미지 페이지 처리', RESULT_VALIDATION: 'PDF 결과 검증', SUCCESS: '결과 게시 완료', FAILED: '변환 실패' };
const date = (value: string) => new Date(value).toLocaleString('ko-KR');
const size = (value: number) => `${(value / 1024 / 1024).toFixed(2)} MiB`;
function savedReference(): JobReference | null {
  try { const value: unknown = JSON.parse(sessionStorage.getItem('convertflow-job') ?? 'null'); return value && typeof value === 'object' && 'jobId' in value && typeof value.jobId === 'string' ? value as JobReference : null; } catch { return null; }
}
export default function App() {
  const client = useQueryClient();
  const [files, setFiles] = useState<UploadEntry[]>([]);
  const [options, setOptions] = useState<Options>({ ...defaultOptions });
  const [reference, setReference] = useState<JobReference | null>(savedReference);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [message, setMessage] = useState('');
  const [dragging, setDragging] = useState(false);
  const [dark, setDark] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [view, setView] = useState<'upload' | 'history'>('upload');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(1);
  const input = useRef<HTMLInputElement>(null);
  const query = useQuery({ queryKey: ['job', reference?.jobId], enabled: !!reference,
    queryFn: async () => (await api.get<Job>(`/jobs/${reference!.jobId}`, { headers: jobHeaders(reference!) })).data,
    refetchInterval: q => terminal(q.state.data?.status) ? false : 1500 });
  const job = query.data;
  const history = useQuery({ queryKey: ['jobs', search, filter, page], enabled: view === 'history', queryFn: async () => (await api.get<JobPage>('/jobs', { params: { search, status: filter || undefined, page, pageSize: 10 } })).data, refetchInterval: 3000 });
  const events = useQuery({ queryKey: ['events', reference?.jobId, job?.status], enabled: !!reference && !!job,
    queryFn: async () => { const all: JobEvent[] = []; let after = 0; let more = true; while (more) { const { data } = await api.get<{ items: JobEvent[]; hasMore: boolean; nextAfter: number }>(`/jobs/${reference!.jobId}/events`, { headers: jobHeaders(reference!), params: { after, limit: 100 } }); all.push(...data.items); more = data.hasMore; after = data.nextAfter; } return all; },
    refetchInterval: terminal(job?.status) ? false : 1500 });
  function selectFiles(selected: FileList | File[]) {
    if (uploading) return;
    const added = Array.from(selected).map(file => ({ id: crypto.randomUUID(), file, error: fileError(file) }));
    setMessage(''); setFiles(previous => [...previous, ...added]);
  }
  function selectJob(next: JobReference) { setReference(next); sessionStorage.setItem('convertflow-job', JSON.stringify(next)); }
  async function submit() {
    if (!files.length || uploadError(files)) return;
    setUploading(true); setMessage(''); setUploadProgress(0);
    try {
      const form = new FormData(); files.forEach(entry => form.append('file', entry.file)); form.append('options', JSON.stringify(options));
      const { data } = await api.post<Job & JobReference>('/jobs', form, { onUploadProgress: e => setUploadProgress(e.total ? Math.round(e.loaded / e.total * 100) : 0) });
      selectJob({ jobId: data.jobId, accessToken: data.accessToken }); setFiles([]); setPage(1); await client.invalidateQueries({ queryKey: ['jobs'] });
    } catch (error) { const text = errorMessage(error); setMessage(text); setFiles(previous => previous.map(entry => text.startsWith(`${entry.file.name}:`) ? { ...entry, error: text } : entry)); } finally { setUploading(false); }
  }
  async function download() {
    if (!reference) return;
    setDownloading(true); setMessage('');
    try {
      const { data } = await api.get(`/jobs/${reference.jobId}/download`, { headers: jobHeaders(reference), responseType: 'blob' });
      const url = URL.createObjectURL(data); const a = document.createElement('a'); a.href = url; a.download = `convertflow-${reference.jobId}.pdf`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setMessage('다운로드에 실패했습니다. 결과 파일과 서버 상태를 확인해 주세요.'); } finally { setDownloading(false); }
  }
  const invalid = uploadError(files);
  const detail = <section className="panel status-panel"><div className="panel-heading"><div><span className="step">02</span><h2>작업 상세</h2></div><span className="live-label">실제 처리 단계</span></div>
    {!reference ? <div className="status-empty"><div className="document-art"><FileText size={44}/><span><Check size={14}/></span></div><h3>다음 문서를 기다리고 있어요</h3><p>파일을 업로드하거나 작업 이력에서<br/>조회할 작업을 선택하세요.</p></div> : query.isPending ? <p role="status">작업 상태를 불러오는 중…</p> : query.isError ? <div role="alert" className="error">{errorMessage(query.error)}<button onClick={() => query.refetch()}>다시 조회</button></div> : job && <div className="job-content"><span className={`badge ${job.status}`}>{labels[job.status]}</span><h3>{job.filename}{job.totalFiles > 1 && ` 외 ${job.totalFiles - 1}개`}</h3><code>{job.jobId}</code><div className="progress-label"><span>{stages[job.stage] ?? job.stage}</span><strong>{job.progress}%</strong></div><progress value={job.progress} max={100}/><p className="stage">파일 {job.processedFiles}/{job.totalFiles} · 페이지 {job.processedPages}/{job.totalPages}{job.durationSeconds !== null && ` · ${job.durationSeconds.toFixed(2)}초`}</p>
      {job.errorCode && <div className="error" role="alert"><strong>{job.errorCode}</strong><p>{job.errorMessage}</p></div>}
      {job.downloadAvailable && <button className="primary" disabled={downloading} onClick={download}><ArrowDownToLine size={17}/>{downloading ? '다운로드 중…' : `PDF 다운로드 · ${job.result?.pageCount ?? job.totalPages}페이지`}</button>}
      <dl className="job-meta"><dt>등록</dt><dd>{date(job.createdAt)}</dd><dt>시작</dt><dd>{job.startedAt ? date(job.startedAt) : '대기 중'}</dd><dt>완료</dt><dd>{job.completedAt ? date(job.completedAt) : '—'}</dd><dt>출력 설정</dt><dd>{job.options && `${job.options.pageSize} / ${job.options.orientation} / 여백 ${job.options.marginMm}mm / ${job.options.fit} / 품질 ${job.options.quality}`}</dd>{job.result && <><dt>결과 크기</dt><dd>{size(job.result.fileSize)}</dd></>}</dl>
      <h4>입력 파일 · 지정한 순서</h4><ol className="detail-files">{job.files?.map(file => <li key={file.fileId}><strong>{file.filename}</strong><small>{file.pageCount}페이지 · {size(file.fileSize)}</small></li>)}</ol>
    </div>}
    <div className="status-foot"><span className="dot"/> 업로드 전송량과 Worker 진행률은 별도로 표시됩니다.</div></section>;
  return <div className={dark ? 'shell dark' : 'shell'}>
    <aside><a href="/" className="brand"><Layers3 size={26}/><span>ConvertFlow<span className="brand-dot">.</span></span></a><span className="workspace">PERSONAL WORKSPACE</span><nav><button className={view === 'upload' ? 'nav-active' : 'nav-link'} onClick={() => setView('upload')}><FileImage size={18}/> 이미지 → PDF <span>01</span></button><button className={view === 'history' ? 'nav-active' : 'nav-link'} onClick={() => setView('history')}><History size={18}/> 작업 이력 <span>02</span></button></nav><div className="sidebar-note"><div className="small-label">DOCUMENT WORKSPACE</div><p>파일 변환은 간단하게.<br/>처리는 백그라운드에서.</p><span>Phase 2 · 다중 파일 및 작업 관리</span></div><footer><span className="avatar">CF</span><div>로컬 워크스페이스<small>개발 환경</small></div></footer></aside>
    <div className="main"><header><span>워크스페이스 <span className="slash">/</span> <strong>{view === 'upload' ? '이미지 → PDF' : '작업 이력'}</strong></span><div className="header-actions"><button className="text-button" onClick={() => setView(view === 'upload' ? 'history' : 'upload')}>{view === 'upload' ? '작업 이력' : '새 변환'}</button><button className="icon-button" aria-label={dark ? '밝은 테마' : '어두운 테마'} onClick={() => setDark(!dark)}>{dark ? <Sun size={19}/> : <Moon size={19}/>}</button></div></header>
    <main><div className="eyebrow">CONVERT YOUR NEXT IDEA</div><div className="heading"><div><h1>{view === 'upload' ? <>여러 이미지를 PDF로, <span>원하는 순서대로.</span></> : <>모든 변환을, <span>한눈에.</span></>}</h1><p>{view === 'upload' ? '이미지와 TIFF 페이지를 하나의 PDF로 묶고 출력 방식을 선택하세요.' : '이 브라우저 작업공간에서 등록한 작업을 조회합니다.'}</p></div><span className="version">IMAGE TO PDF</span></div>
    {view === 'upload' ? <div className="work-grid"><section className="panel upload-panel"><div className="panel-heading"><div><span className="step">01</span><h2>파일 업로드</h2></div><span className="muted">최대 20개 · 100페이지</span></div>
      <input ref={input} type="file" multiple accept=".png,.jpg,.jpeg,.bmp,.webp,.tif,.tiff" hidden onChange={e => { if (e.target.files) selectFiles(e.target.files); e.target.value = ''; }}/>
      <button disabled={uploading} className={`drop-zone ${dragging ? 'dragging' : ''}`} onClick={() => input.current?.click()} onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); selectFiles(e.dataTransfer.files); }}><span className="upload-icon"><UploadCloud size={30}/></span><strong>이미지를 여기에 끌어다 놓으세요</strong><span>또는 <em>여러 파일 찾아보기</em></span><small>PNG, JPG, BMP, WEBP, TIFF · 개별 20 MiB / 전체 100 MiB</small></button>
      {files.length ? <div className="file-selection"><div className="selection-heading"><span>{files.length}개 · {size(files.reduce((sum, entry) => sum + entry.file.size, 0))}</span><button className="text-button" disabled={uploading} onClick={() => setFiles([])}>전체 삭제</button></div><ol>{files.map((entry, index) => <li key={entry.id} className="selected"><span className="file-order">{index + 1}</span><div><strong>{entry.file.name}</strong><small>{size(entry.file.size)}</small>{entry.error && <span className="file-error">{entry.error}</span>}</div><button className="icon-button" disabled={uploading || index === 0} aria-label={`${entry.file.name} 위로`} onClick={() => setFiles(moveEntry(files, index, -1))}><ArrowUp size={15}/></button><button className="icon-button" disabled={uploading || index === files.length - 1} aria-label={`${entry.file.name} 아래로`} onClick={() => setFiles(moveEntry(files, index, 1))}><ArrowDown size={15}/></button><button className="icon-button" disabled={uploading} aria-label={`${entry.file.name} 제거`} onClick={() => setFiles(files.filter(file => file.id !== entry.id))}><X size={15}/></button></li>)}</ol></div> : <div className="empty-selection"><FileImage size={17}/> 업로드 순서가 PDF 페이지 순서가 됩니다.</div>}
      {invalid && <p className="file-error" role="alert">{invalid}</p>}
      <fieldset className="options" disabled={uploading}><legend>PDF 출력 설정</legend><label>페이지 크기<select value={options.pageSize} onChange={e => setOptions({ ...options, pageSize: e.target.value as Options['pageSize'] })}><option value="original">원본 크기 (96 DPI)</option><option>A4</option><option>Letter</option></select></label><label>방향<select value={options.orientation} onChange={e => setOptions({ ...options, orientation: e.target.value as Options['orientation'] })}><option value="auto">기본 방향 (원본 또는 세로)</option><option value="portrait">세로</option><option value="landscape">가로</option></select></label><label>여백 (mm)<input type="number" min={0} max={50} step={1} value={options.marginMm} onChange={e => setOptions({ ...options, marginMm: Number(e.target.value) })}/></label><label>이미지 배치<select value={options.fit} onChange={e => setOptions({ ...options, fit: e.target.value as Options['fit'] })}><option value="contain">전체 맞춤 · 비율 유지</option><option value="cover">영역 채우기 · 중앙 자르기</option></select></label><label className="quality">출력 품질 · {options.quality}<input type="range" min={1} max={100} value={options.quality} onChange={e => setOptions({ ...options, quality: Number(e.target.value) })}/></label></fieldset>
      <p className="option-note">TIFF의 모든 페이지를 순서대로 변환합니다. 원본 크기에 큰 여백을 지정하면 변환이 실패할 수 있습니다.</p>
      {uploading && <div role="status" className="upload-progress">업로드 {uploadProgress}%<progress max={100} value={uploadProgress}/></div>}
      <button className="primary" onClick={submit} disabled={!files.length || !!invalid || uploading || options.marginMm < 0 || options.marginMm > 50}>{uploading ? <LoaderCircle className="spin" size={17}/> : <ArrowRight size={18}/>} {uploading ? '업로드 중…' : '하나의 PDF로 변환'}</button><p className="privacy">파일은 로컬 공유 스토리지에 저장되며 외부 서비스로 전송되지 않습니다.</p></section>{detail}</div> : <><section className="panel history-panel"><div className="panel-heading"><h2>작업 목록</h2><span className="muted">총 {history.data?.total ?? 0}건</span></div><div className="filters"><label>검색<input placeholder="파일명 또는 Job ID" maxLength={120} value={search} onChange={e => { setSearch(e.target.value); setPage(1); }}/></label><label>상태<select value={filter} onChange={e => { setFilter(e.target.value); setPage(1); }}><option value="">전체 상태</option>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div>
      {history.isPending ? <p role="status">작업 목록을 불러오는 중…</p> : history.isError ? <div className="error" role="alert">{errorMessage(history.error)}<button onClick={() => history.refetch()}>다시 조회</button></div> : history.data && <><div className="table-scroll"><table><thead><tr><th>파일 / Job ID</th><th>상태</th><th>진행률</th><th>등록 시간</th><th>처리 시간</th><th>실패 원인</th></tr></thead><tbody>{history.data.items.map(item => <tr key={item.jobId}><td><button className="job-link" onClick={() => selectJob({ jobId: item.jobId })}>{item.filename}{item.totalFiles > 1 && ` 외 ${item.totalFiles - 1}개`}</button><small>{item.jobId}</small></td><td><span className={`badge ${item.status}`}>{labels[item.status]}</span></td><td>{item.progress}%<progress max={100} value={item.progress}/></td><td>{date(item.createdAt)}</td><td>{item.durationSeconds !== null ? `${item.durationSeconds.toFixed(2)}초` : '—'}</td><td>{item.errorCode ?? '—'}</td></tr>)}</tbody></table></div>{!history.data.items.length && <div className="history-empty">{search || filter ? '검색 조건에 맞는 작업이 없습니다.' : '이 작업공간에서 등록한 작업이 없습니다. 새 변환을 시작하세요.'}</div>}<div className="pagination"><button className="text-button" disabled={page <= 1} onClick={() => setPage(page - 1)}>이전</button><span>{page} / {Math.max(1, Math.ceil(history.data.total / 10))}</span><button className="text-button" disabled={page * 10 >= history.data.total} onClick={() => setPage(page + 1)}>다음</button></div></>}
    </section><div className="history-detail">{detail}</div></>}
    {message && <div className="error" role="alert">{message}</div>}
    {job && <section className="panel timeline-panel"><div className="panel-heading"><h2>작업 이벤트 타임라인</h2><span className="muted">{job.jobId.slice(0, 8)}</span></div>{events.isPending ? <p role="status">이력을 불러오는 중…</p> : events.isError ? <div role="alert" className="error">이력을 불러오지 못했습니다.<button onClick={() => events.refetch()}>다시 조회</button></div> : <ol className="timeline">{events.data?.map(event => <li key={event.eventId}><time>{date(event.createdAt)}</time><span className="event-type">{event.type}</span><strong>{event.message}</strong>{event.details.processedPages !== undefined && <small>페이지 {event.details.processedPages}/{event.details.totalPages}</small>}</li>)}</ol>}</section>}
    <section className="how"><div><span className="small-label">A SIMPLE FLOW</span><h2>업로드부터 다운로드까지</h2></div><div><b>1</b><span><strong>이미지와 순서 선택</strong><small>파일과 출력 설정을 준비하세요.</small></span></div><ArrowRight size={18}/><div><b>2</b><span><strong>백그라운드 변환</strong><small>페이지별 진행 상황을 확인하세요.</small></span></div><ArrowRight size={18}/><div><b>3</b><span><strong>결과와 이력 확인</strong><small>완성된 PDF를 저장하세요.</small></span></div></section><div className="bottom-line"><span>ConvertFlow · Asynchronous Document Processing</span><span>Built for a better document flow.</span></div></main></div></div>;
}
