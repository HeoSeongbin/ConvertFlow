import axios from 'axios';
export const api = axios.create({ baseURL: '/api/v1', timeout: 120000 });
export type JobStatus = 'QUEUED' | 'PROCESSING' | 'SUCCESS' | 'FAILED' | 'RETRY_WAIT' | 'CANCEL_REQUESTED' | 'CANCELLED';
export interface Options { pageSize: 'original' | 'A4' | 'Letter'; orientation: 'auto' | 'portrait' | 'landscape'; marginMm: number; fit: 'contain' | 'cover'; quality: number }
export const defaultOptions: Options = { pageSize: 'original', orientation: 'auto', marginMm: 0, fit: 'contain', quality: 90 };
export interface JobFile { fileId: string; filename: string; fileSize: number; mimeType: string; pageCount: number; sortOrder: number; checksum: string }
export interface Job { jobId: string; status: JobStatus; runGeneration: number; attemptCount: number; autoRetryCount: number; nextRetryAt: string | null; canRetry: boolean; canCancel: boolean; sourceAvailable?: boolean; retryBlockedReason?: string | null; stage: string; progress: number; filename: string; createdAt: string; startedAt: string | null; completedAt: string | null; durationSeconds: number | null; totalFiles: number; processedFiles: number; totalPages: number; processedPages: number; errorCode: string | null; errorMessage: string | null; downloadAvailable: boolean; options?: Options; files?: JobFile[]; result?: { fileSize: number; pageCount: number; checksum: string } | null }
export interface JobReference { jobId: string; accessToken?: string }
export interface JobPage { items: Job[]; total: number; page: number; pageSize: number }
export interface JobEvent { eventId: string; attemptId?: string | null; sequence: number; type: string; message: string; createdAt: string; details: { errorCode?: string; filename?: string; processedPages?: number; totalPages?: number } }
export const terminal = (status?: JobStatus) => status === 'SUCCESS' || status === 'FAILED' || status === 'CANCELLED';
export const jobHeaders = (reference: JobReference) => reference.accessToken ? { 'X-Job-Token': reference.accessToken } : {};
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    let data = error.response?.data;
    if (data instanceof ArrayBuffer && data.byteLength <= 64 * 1024) { try { data = JSON.parse(new TextDecoder().decode(data)); } catch { data = undefined; } }
    const detail = data?.detail;
    return typeof detail?.message === 'string' ? detail.message : Array.isArray(detail) ? '입력값과 파일 개수를 확인해 주세요.' : '서버에 연결할 수 없습니다. 서비스 상태를 확인해 주세요.';
  }
  return '요청을 처리하지 못했습니다.';
}

export interface Attempt { attemptId: string; attemptNumber: number; generation: number; origin: 'INITIAL' | 'AUTO' | 'MANUAL' | 'LEGACY'; workerName: string; status: string; startedAt: string | null; finishedAt: string | null; errorCode: string | null; errorMessage: string | null; retryable: boolean }
export interface AttemptPage { items: Attempt[]; total: number; page: number; pageSize: number }
