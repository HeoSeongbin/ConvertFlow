export interface UploadEntry { id: string; file: File; error?: string }
export function fileError(file: Pick<File, 'name' | 'size'>): string | undefined {
  if (file.size > 20 * 1024 * 1024) return '파일은 최대 20 MiB입니다.';
  if (!/\.(png|jpe?g|bmp|webp|tiff?)$/i.test(file.name)) return '지원하지 않는 이미지 형식입니다.';
}
export function moveEntry<T>(entries: T[], index: number, direction: -1 | 1): T[] {
  const target = index + direction;
  if (index < 0 || index >= entries.length || target < 0 || target >= entries.length) return entries;
  const next = [...entries]; [next[index], next[target]] = [next[target], next[index]]; return next;
}
export function uploadError(entries: UploadEntry[]): string | undefined {
  if (entries.length > 20) return '파일은 최대 20개입니다.';
  if (entries.reduce((total, entry) => total + entry.file.size, 0) > 100 * 1024 * 1024) return '전체 파일은 최대 100 MiB입니다.';
  if (entries.some(entry => entry.error)) return '오류가 있는 파일을 제거해 주세요.';
}
