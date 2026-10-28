import type { Job, JobStatus } from '../../services/api';

export const PREVIEW_LIMIT = 32 * 1024 * 1024;
export function durationLabel(job: Pick<Job, 'durationSeconds' | 'status' | 'startedAt'>): string {
  if (job.durationSeconds !== null) return `${job.durationSeconds.toFixed(2)}초`;
  if (job.status === 'CANCELLED' && !job.startedAt) return '실행 안 함';
  if (job.status === 'PROCESSING' || job.status === 'CANCEL_REQUESTED') return '실행 중';
  if (job.status === 'QUEUED' || job.status === 'RETRY_WAIT') return '대기 중';
  return '시간 기록 없음';
}
export function previewGeometry(width: number, height: number, available: number, ratio = 1) {
  const density = Math.min(2, Math.max(1, ratio));
  const scale = Math.min(Math.max(240, available) / width, 1200 / width, Math.sqrt(2_000_000 / (width * height)) / density);
  return { scale: scale * density, cssWidth: width * scale, cssHeight: height * scale };
}
export function errorHint(code: string | null): string {
  switch (code) {
    case 'INVALID_OPTIONS': return '여백이나 페이지 크기를 조정한 뒤 새 작업으로 등록하세요.';
    case 'INVALID_FILE': case 'DECODE_FAILED': return '이미지를 다시 열어 정상 파일인지 확인한 뒤 재업로드하세요.';
    case 'SOURCE_MISSING': return '원본 파일을 찾을 수 없습니다. 파일을 다시 선택해 등록하세요.';
    case 'WORKER_LEASE_EXPIRED': return '이전 실행의 Lease가 만료되었습니다. 예약된 재시도와 처리 시도 이력을 확인하세요.';
    case 'STORAGE_ERROR': return '저장소 상태나 권한을 복구한 뒤 재시도 가능 여부를 확인하세요.';
    default: return '아래 원인과 처리 시도 이력을 확인하세요. 재시도해도 이전 오류는 보존됩니다.';
  }
}
export function progressNote(status: JobStatus): string {
  if (status === 'QUEUED') return '파일을 접수했습니다. Worker가 실행할 때까지 기다립니다.';
  if (status === 'RETRY_WAIT') return 'DB에 저장한 예약 시각까지 대기합니다. 아직 다음 실행을 시작하지 않았습니다.';
  if (status === 'CANCEL_REQUESTED') return '취소 요청을 전달했습니다. Worker가 다음 처리 경계에서 확인합니다.';
  if (status === 'CANCELLED') return '작업을 취소했습니다. 진행률은 마지막 실제 처리 시점의 값입니다.';
  if (status === 'SUCCESS') return '전체 PDF를 검증하고 결과를 게시했습니다.';
  if (status === 'FAILED') return '이번 실행을 마치지 못했습니다. 실패한 단계와 이전 오류를 확인하세요.';
  return '실제로 처리한 페이지와 결과 검증 단계에 따라 진행률을 갱신합니다.';
}
