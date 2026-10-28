import { useEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy, PDFDocumentLoadingTask, PDFPageProxy, RenderTask } from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { api, errorMessage, jobHeaders, type JobReference } from '../../services/api';
import { previewGeometry } from './presentation';

export default function PDFPreview({ reference }: { reference: JobReference }) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState('');
  const [rendering, setRendering] = useState(true);
  const [width, setWidth] = useState(600);
  const [retry, setRetry] = useState(0);
  const container = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let stopped = false;
    let task: PDFDocumentLoadingTask | undefined;
    const controller = new AbortController();
    setError(''); setPdf(null); setPage(1);
    void (async () => {
      try {
        const { data } = await api.get<ArrayBuffer>(`/jobs/${reference.jobId}/download`, { headers: jobHeaders(reference), responseType: 'arraybuffer', signal: controller.signal });
        const lib = await import('pdfjs-dist');
        if (stopped) return;
        lib.GlobalWorkerOptions.workerSrc = workerUrl;
        task = lib.getDocument({ data: new Uint8Array(data), enableXfa: false });
        const document = await task.promise;
        if (!stopped) setPdf(document);
      } catch (failure) { if (!stopped) setError(`미리보기를 불러오지 못했습니다. ${errorMessage(failure)} PDF 다운로드도 이용할 수 있습니다.`); }
    })();
    return () => { stopped = true; controller.abort(); void task?.destroy().catch(() => {}); };
  }, [reference.jobId, reference.accessToken, retry]);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(entries => setWidth(Math.round(entries[0].contentRect.width)));
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!pdf || !canvas.current) return;
    let stopped = false;
    let task: RenderTask | undefined;
    let loaded: PDFPageProxy | undefined;
    const target = canvas.current;
    setRendering(true); setError('');
    void (async () => {
      try {
        loaded = await pdf.getPage(page);
        if (stopped) return;
        const natural = loaded.getViewport({ scale: 1 });
        const geometry = previewGeometry(natural.width, natural.height, width, window.devicePixelRatio);
        const viewport = loaded.getViewport({ scale: geometry.scale });
        target.width = Math.floor(viewport.width); target.height = Math.floor(viewport.height);
        target.style.width = `${geometry.cssWidth}px`; target.style.height = `${geometry.cssHeight}px`;
        task = loaded.render({ canvas: target, viewport });
        await task.promise;
        if (!stopped) setRendering(false);
      } catch (failure) { if (!stopped) { setRendering(false); setError('이 페이지를 표시하지 못했습니다. 다시 불러오거나 PDF를 다운로드하세요.'); } }
    })();
    return () => { stopped = true; if (task) { task.cancel(); void task.promise.catch(() => {}).then(() => loaded?.cleanup()); } else loaded?.cleanup(); };
  }, [pdf, page, width]);
  return <div className="pdf-viewer">
    {error ? <div className="error" role="alert">{error}<button className="text-button" onClick={() => setRetry(value => value + 1)}>미리보기 다시 불러오기</button></div> : !pdf ? <p role="status">검증된 PDF를 불러오는 중…</p> : null}
    {pdf && <div className="preview-toolbar"><button className="text-button" disabled={page <= 1} onClick={() => setPage(value => value - 1)}>이전 페이지</button><span aria-live="polite">{page} / {pdf.numPages} 페이지</span><button className="text-button" disabled={page >= pdf.numPages} onClick={() => setPage(value => value + 1)}>다음 페이지</button></div>}
    <div className="preview-canvas" ref={container} aria-busy={rendering && !!pdf}>{pdf && <><canvas key={`${page}-${width}`} ref={canvas} role="img" aria-label={`PDF ${page}페이지 미리보기`}/>{rendering && !error && <p role="status">페이지를 렌더링하는 중…</p>}</>}</div>
    <p className="monitor-note">브라우저에서 한 페이지씩 표시합니다. 원본 PDF의 크기·내용은 바뀌지 않습니다.</p>
  </div>;
}
