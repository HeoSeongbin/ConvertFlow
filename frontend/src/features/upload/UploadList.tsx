import { useEffect, useState } from 'react';
import { ArrowDown, ArrowUp, FileImage, X } from 'lucide-react';
import { moveEntry, type UploadEntry } from './files';
function Thumbnail({ file }: { file: File }) {
  const [url, setUrl] = useState('');
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (/\.tiff?$/i.test(file.name)) return;
    const object = URL.createObjectURL(file);
    setUrl(object); setFailed(false);
    return () => URL.revokeObjectURL(object);
  }, [file]);
  return url && !failed ? <img className="upload-thumbnail" src={url} loading="lazy" decoding="async" alt={`${file.name} 미리보기`} onError={() => setFailed(true)}/> : <span className="upload-thumbnail placeholder"><FileImage size={20}/></span>;
}
export default function UploadList({ files, disabled, setFiles }: { files: UploadEntry[]; disabled: boolean; setFiles: (files: UploadEntry[]) => void }) {
  const [announcement, setAnnouncement] = useState('');
  function move(index: number, direction: -1 | 1) {
    const next = moveEntry(files, index, direction);
    setFiles(next); setAnnouncement(`${files[index].file.name}, ${index + direction + 1}번째로 이동했습니다.`);
  }
  const invalid = files.filter(entry => entry.error).length;
  return <div className="file-selection"><div className="selection-heading"><span>{files.length}개 · {(files.reduce((sum, entry) => sum + entry.file.size, 0) / 1024 / 1024).toFixed(2)} MiB</span><div>{invalid > 0 && <button className="text-button" disabled={disabled} onClick={() => setFiles(files.filter(entry => !entry.error))}>오류 파일 {invalid}개 제거</button>}<button className="text-button" disabled={disabled} onClick={() => setFiles([])}>전체 삭제</button></div></div>
    <p className="monitor-note">이 순서대로 PDF에 들어갑니다. TIFF는 파일 안의 모든 페이지를 유지합니다.</p>
    <ol>{files.map((entry, index) => <li key={entry.id} className={`selected ${entry.error ? 'invalid-entry' : ''}`}><span className="file-order">{index + 1}</span><Thumbnail file={entry.file}/><div><strong title={entry.file.name}>{entry.file.name}</strong><small>{(entry.file.size / 1024 / 1024).toFixed(2)} MiB{ /\.tiff?$/i.test(entry.file.name) && ' · 모든 TIFF 페이지'}</small>{entry.error && <span className="file-error">{entry.error}</span>}</div><div className="file-controls"><button className="icon-button" disabled={disabled || index === 0} aria-label={`${entry.file.name} 위로`} onClick={() => move(index, -1)}><ArrowUp size={15}/></button><button className="icon-button" disabled={disabled || index === files.length - 1} aria-label={`${entry.file.name} 아래로`} onClick={() => move(index, 1)}><ArrowDown size={15}/></button><button className="icon-button" disabled={disabled} aria-label={`${entry.file.name} 제거`} onClick={() => setFiles(files.filter(file => file.id !== entry.id))}><X size={15}/></button></div></li>)}</ol>
    <span className="sr-only" role="status">{announcement}</span>
  </div>;
}
