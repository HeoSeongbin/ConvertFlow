import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Activity, Server, ArrowRight, FileImage, History, Layers3, LoaderCircle, RotateCcw, Moon, Sun, UploadCloud } from 'lucide-react';
import { api, defaultOptions, errorMessage, jobHeaders, terminal, type Job, type JobPage, type JobReference, type Options } from '../services/api';
import AttemptHistory from '../features/jobs/AttemptHistory';
import Monitoring from '../features/monitoring/Monitoring';
import JobDetail from '../features/jobs/JobDetail';
import HistoryCards from '../features/jobs/HistoryCards';
import EventTimeline from '../features/jobs/EventTimeline';
import UploadList from '../features/upload/UploadList';
import { fileError, uploadError, type UploadEntry } from '../features/upload/files';
const labels = { QUEUED: '대기 중', PROCESSING: '변환 중', SUCCESS: '변환 완료', FAILED: '실패', RETRY_WAIT: '재시도 대기', CANCEL_REQUESTED: '취소 요청', CANCELLED: '취소됨' };
const date = (value: string) => new Date(value).toLocaleString('ko-KR');
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
  const [dark, setDark] = useState(() => { try { const stored = localStorage.getItem('convertflow-theme'); return stored ? stored === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches; } catch { return false; } });
  useEffect(() => { try { localStorage.setItem('convertflow-theme', dark ? 'dark' : 'light'); } catch { /* Storage may be disabled. */ } document.documentElement.style.colorScheme = dark ? 'dark' : 'light'; }, [dark]);

  const [actionPending, setActionPending] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [view, setView] = useState<'upload' | 'history' | 'retry' | 'dashboard' | 'workers'>('upload');
  useEffect(() => { window.scrollTo({ top: 0 }); }, [view]);
  const monitoringView = view === 'dashboard' || view === 'workers';
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(1);
  const input = useRef<HTMLInputElement>(null);
  const query = useQuery({ queryKey: ['job', reference?.jobId], enabled: !!reference && !monitoringView,
    queryFn: async () => (await api.get<Job>(`/jobs/${reference!.jobId}`, { headers: jobHeaders(reference!) })).data,
    refetchInterval: q => terminal(q.state.data?.status) ? false : 1500 });
  const job = query.data;
  const history = useQuery({ queryKey: ['jobs', view, search, filter, page], enabled: view === 'history' || view === 'retry', queryFn: async () => (await api.get<JobPage>('/jobs', { params: { search, status: filter || undefined, page, pageSize: 10, retryCenter: view === 'retry' } })).data, refetchInterval: 3000 });
  function selectFiles(selected: FileList | File[]) {
    if (uploading) return;
    const added = Array.from(selected).map(file => ({ id: crypto.randomUUID(), file, error: fileError(file) }));
    setMessage(''); setFiles(previous => [...previous, ...added]);
  }
  function selectJob(next: JobReference) { setReference(next); try { sessionStorage.setItem('convertflow-job', JSON.stringify(next)); } catch { /* Current selection still works without storage. */ } }
  function openJob(next: JobReference) { selectJob(next); requestAnimationFrame(() => { document.getElementById('job-detail')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); document.getElementById('job-detail')?.focus({ preventScroll: true }); }); }
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
  async function act(action: 'retry' | 'cancel', target: JobReference, generation: number) {
    setActionPending(true); setMessage('');
    try {
      const { data } = await api.post<Job>(`/jobs/${target.jobId}/${action}`, { expectedGeneration: generation }, { headers: jobHeaders(target) });
      openJob(target);
      client.setQueryData<Job>(['job', target.jobId], old => old ? { ...old, ...data } : data);
      await Promise.all([client.invalidateQueries({ queryKey: ['job', target.jobId] }), client.invalidateQueries({ queryKey: ['jobs'] }), client.invalidateQueries({ queryKey: ['attempts', target.jobId] }), client.invalidateQueries({ queryKey: ['events', target.jobId] })]);
    } catch (error) { setMessage(errorMessage(error)); await client.invalidateQueries({ queryKey: ['job', target.jobId] }); } finally { setActionPending(false); }
  }
  const invalid = uploadError(files);
  const detail = <JobDetail key={reference?.jobId ?? 'empty'} job={job} reference={reference} pending={query.isPending} error={query.isError ? query.error : null} refresh={() => void query.refetch()} download={() => void download()} downloading={downloading} actionPending={actionPending} act={action => { if (reference && job) void act(action, reference, job.runGeneration); }}/>;
  return <div className={dark ? 'shell dark' : 'shell'}><a className="skip-link" href="#main-content">본문으로 이동</a>
    <aside><a href="/" className="brand"><Layers3 size={26}/><span>ConvertFlow<span className="brand-dot">.</span></span></a><span className="workspace">PERSONAL WORKSPACE</span><nav aria-label="주 메뉴"><button className={view === 'upload' ? 'nav-active' : 'nav-link'} onClick={() => setView('upload')}><FileImage size={18}/> 이미지 → PDF <span>01</span></button><button className={view === 'history' ? 'nav-active' : 'nav-link'} onClick={() => { setView('history'); setFilter(''); setSearch(''); setPage(1); }}><History size={18}/> 작업 이력 <span>02</span></button><button className={view === 'retry' ? 'nav-active' : 'nav-link'} onClick={() => { setView('retry'); setFilter(''); setSearch(''); setPage(1); }}><RotateCcw size={18}/> Retry Center <span>03</span></button><button className={view === 'dashboard' ? 'nav-active' : 'nav-link'} onClick={() => setView('dashboard')}><Activity size={18}/> Dashboard <span>04</span></button><button className={view === 'workers' ? 'nav-active' : 'nav-link'} onClick={() => setView('workers')}><Server size={18}/> Worker Monitoring <span>05</span></button></nav><div className="sidebar-note"><div className="small-label">DOCUMENT WORKSPACE</div><p>파일 변환은 간단하게.<br/>처리는 백그라운드에서.</p><span>Phase 6 · 문서 작업 콘솔</span></div><footer><span className="avatar">CF</span><div>로컬 워크스페이스<small>개발 환경</small></div></footer></aside>
    <div className="main"><header><span>워크스페이스 <span className="slash">/</span> <strong>{view === 'dashboard' ? 'Dashboard' : view === 'workers' ? 'Worker Monitoring' : view === 'upload' ? '이미지 → PDF' : view === 'retry' ? 'Retry Center' : '작업 이력'}</strong></span><div className="header-actions"><select className="mobile-nav" aria-label="화면 선택" value={view} onChange={e => setView(e.target.value as typeof view)}><option value="upload">새 변환</option><option value="history">작업 이력</option><option value="retry">Retry Center</option><option value="dashboard">Dashboard</option><option value="workers">Worker Monitoring</option></select><button className="text-button" onClick={() => setView(view === 'upload' ? 'history' : 'upload')}>{view === 'upload' ? '작업 이력' : '새 변환'}</button><button className="icon-button" aria-label={dark ? '밝은 테마' : '어두운 테마'} onClick={() => setDark(!dark)}>{dark ? <Sun size={19}/> : <Moon size={19}/>}</button></div></header>
    <main id="main-content" tabIndex={-1}><div className="eyebrow">CONVERT YOUR NEXT IDEA</div><div className="heading"><div><h1>{view === 'dashboard' ? <>작업 흐름을, <span>실제 데이터로.</span></> : view === 'workers' ? <>백그라운드의 지금, <span>Worker 관측.</span></> : view === 'upload' ? <>여러 이미지를 PDF로, <span>원하는 순서대로.</span></> : view === 'retry' ? <>실패를 추적하고, <span>안전하게 다시.</span></> : <>모든 변환을, <span>한눈에.</span></>}</h1><p>{monitoringView ? 'DB 이력과 실제 수집 시각을 기준으로 처리 현황을 확인합니다.' : view === 'upload' ? '이미지와 TIFF 페이지를 하나의 PDF로 묶고 출력 방식을 선택하세요.' : view === 'retry' ? '실패 원인과 재시도 가능 여부를 확인하고 처리 시도 이력을 보존합니다.' : '이 브라우저 작업공간에서 등록한 작업을 조회합니다.'}</p></div><span className="version">IMAGE TO PDF</span></div>
    {message && <div className="error global-notice" role="alert"><span>{message}</span><button className="text-button" aria-label="오류 알림 닫기" onClick={() => setMessage('')}>닫기</button></div>}
    {monitoringView ? <Monitoring mode={view === 'workers' ? 'workers' : 'dashboard'} selectJob={jobId => { selectJob({ jobId }); setView('history'); setSearch(''); setFilter(''); setPage(1); }}/> : view === 'upload' ? <div className="work-grid"><section className="panel upload-panel" aria-label="파일 업로드"><div className="panel-heading"><div><span className="step">01</span><h2>파일 업로드</h2></div><span className="muted">최대 20개 · 100페이지</span></div>
      <input ref={input} type="file" multiple accept=".png,.jpg,.jpeg,.bmp,.webp,.tif,.tiff" hidden onChange={e => { if (e.target.files) selectFiles(e.target.files); e.target.value = ''; }}/>
      <button disabled={uploading} className={`drop-zone ${dragging ? 'dragging' : ''}`} onClick={() => input.current?.click()} onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); selectFiles(e.dataTransfer.files); }}><span className="upload-icon"><UploadCloud size={30}/></span><strong>이미지를 여기에 끌어다 놓으세요</strong><span>또는 <em>여러 파일 찾아보기</em></span><small>PNG, JPG, BMP, WEBP, TIFF · 개별 20 MiB / 전체 100 MiB</small></button>
      {files.length ? <UploadList files={files} disabled={uploading} setFiles={setFiles}/> : <div className="empty-selection"><FileImage size={17}/> 업로드 순서가 PDF 페이지 순서가 됩니다.</div>}
      {invalid && <p className="file-error" role="alert">{invalid}</p>}
      <fieldset className="options" disabled={uploading}><legend>PDF 출력 설정</legend><label>페이지 크기<select value={options.pageSize} onChange={e => setOptions({ ...options, pageSize: e.target.value as Options['pageSize'] })}><option value="original">원본 크기 (96 DPI)</option><option>A4</option><option>Letter</option></select></label><label>방향<select value={options.orientation} onChange={e => setOptions({ ...options, orientation: e.target.value as Options['orientation'] })}><option value="auto">기본 방향 (원본 또는 세로)</option><option value="portrait">세로</option><option value="landscape">가로</option></select></label><label>여백 (mm)<input type="number" min={0} max={50} step={1} value={options.marginMm} onChange={e => setOptions({ ...options, marginMm: Number(e.target.value) })}/></label><label>이미지 배치<select value={options.fit} onChange={e => setOptions({ ...options, fit: e.target.value as Options['fit'] })}><option value="contain">전체 맞춤 · 비율 유지</option><option value="cover">영역 채우기 · 중앙 자르기</option></select></label><label className="quality">출력 품질 · {options.quality}<input type="range" min={1} max={100} value={options.quality} onChange={e => setOptions({ ...options, quality: Number(e.target.value) })}/></label></fieldset>
      <p className="option-note">TIFF의 모든 페이지를 순서대로 변환합니다. 원본 크기에 큰 여백을 지정하면 변환이 실패할 수 있습니다.</p>
      {uploading && <div role="status" className="upload-progress">업로드 {uploadProgress}%<progress aria-label="파일 전송 진행률" max={100} value={uploadProgress}/></div>}
      <button className="primary" onClick={submit} disabled={!files.length || !!invalid || uploading || options.marginMm < 0 || options.marginMm > 50}>{uploading ? <LoaderCircle className="spin" size={17}/> : <ArrowRight size={18}/>} {uploading ? uploadProgress === 100 ? '파일 전송 완료 · 서버 검증 중…' : '업로드 중…' : '하나의 PDF로 변환'}</button><p className="privacy">파일은 로컬 공유 스토리지에 저장되며 외부 서비스로 전송되지 않습니다.</p></section>{detail}</div> : <><section className="panel history-panel"><div className="panel-heading"><h2>{view === 'retry' ? '실패 및 자동 재시도 대기 작업' : '작업 목록'}</h2><span className="muted">총 {history.data?.total ?? 0}건</span></div><div className="filters"><label>검색<input placeholder="파일명 또는 Job ID" maxLength={120} value={search} onChange={e => { setSearch(e.target.value); setPage(1); }}/></label><label>상태<select value={filter} onChange={e => { setFilter(e.target.value); setPage(1); }}><option value="">전체 상태</option>{Object.entries(labels).filter(([value]) => view !== 'retry' || ['FAILED', 'RETRY_WAIT'].includes(value)).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div>
      {history.isPending ? <p role="status">작업 목록을 불러오는 중…</p> : history.isError ? <div className="error" role="alert">{errorMessage(history.error)}<button onClick={() => history.refetch()}>다시 조회</button></div> : history.data && <><HistoryCards jobs={history.data.items} selected={reference?.jobId} pending={actionPending} select={jobId => openJob({ jobId })} retry={item => void act('retry', {jobId:item.jobId}, item.runGeneration)}/><div className="table-scroll history-table"><table><thead><tr><th scope="col">파일 / Job ID</th><th scope="col">상태</th><th scope="col">진행률</th><th scope="col">등록 시간</th><th scope="col">처리 시간</th><th scope="col">실패 원인 / 재처리</th></tr></thead><tbody>{history.data.items.map(item => <tr key={item.jobId} className={reference?.jobId === item.jobId ? 'selected-job-row' : undefined}><td><button className="job-link" aria-current={reference?.jobId === item.jobId ? 'true' : undefined} onClick={() => openJob({ jobId: item.jobId })}>{item.filename}{item.totalFiles > 1 && ` 외 ${item.totalFiles - 1}개`}</button><small>{item.jobId}</small></td><td><span className={`badge ${item.status}`}>{labels[item.status]}</span></td><td>{item.progress}%<progress max={100} value={item.progress}/></td><td>{date(item.createdAt)}</td><td>{item.durationSeconds !== null ? `${item.durationSeconds.toFixed(2)}초` : '—'}</td><td>{item.errorCode ?? '—'}{item.errorCode && <small>{item.errorMessage}</small>}{item.canRetry ? <button className="text-button" disabled={actionPending} onClick={() => act('retry', { jobId: item.jobId }, item.runGeneration)}>재시도</button> : item.status === 'FAILED' ? <small>같은 입력으로 재시도 불가</small> : null}{item.nextRetryAt && <small>예약 {date(item.nextRetryAt)}</small>}</td></tr>)}</tbody></table></div>{!history.data.items.length && <div className="history-empty">{search || filter ? '검색 조건에 맞는 작업이 없습니다.' : view === 'retry' ? '실패 또는 자동 재시도 대기 작업이 없습니다.' : '이 작업공간에서 등록한 작업이 없습니다. 새 변환을 시작하세요.'}</div>}<div className="pagination"><button className="text-button" disabled={page <= 1} onClick={() => setPage(page - 1)}>이전</button><span>{page} / {Math.max(1, Math.ceil(history.data.total / 10))}</span><button className="text-button" disabled={page * 10 >= history.data.total} onClick={() => setPage(page + 1)}>다음</button></div></>}
    </section><div className="history-detail">{detail}</div></>}
    {!monitoringView && job && reference && <AttemptHistory key={reference.jobId} reference={reference} job={job}/>}
    {!monitoringView && job && reference && <EventTimeline key={`${reference.jobId}-${job.runGeneration}`} reference={reference} job={job}/>}
    <section className="how"><div><span className="small-label">A SIMPLE FLOW</span><h2>업로드부터 다운로드까지</h2></div><div><b>1</b><span><strong>이미지와 순서 선택</strong><small>파일과 출력 설정을 준비하세요.</small></span></div><ArrowRight size={18}/><div><b>2</b><span><strong>백그라운드 변환</strong><small>페이지별 진행 상황을 확인하세요.</small></span></div><ArrowRight size={18}/><div><b>3</b><span><strong>결과와 이력 확인</strong><small>완성된 PDF를 저장하세요.</small></span></div></section><div className="bottom-line"><span>ConvertFlow · Asynchronous Document Processing</span><span>Built for a better document flow.</span></div></main></div></div>;
}
