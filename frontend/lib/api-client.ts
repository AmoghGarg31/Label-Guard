import type { Analytics, HistoryItem, Inspection, PackageScope, ReviewStatus, RuleInfo, SystemStatus } from './types';

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
    this.name = 'ApiError';
  }
}

function detailMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object') return fallback;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') return detail[0].msg;
  return fallback;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      cache: 'no-store', ...options,
      headers: options.body instanceof FormData ? options.headers : { 'Content-Type': 'application/json', ...options.headers },
    });
  } catch {
    throw new Error(`LabelGuard API is unreachable at ${API_BASE_URL}. Start the backend and retry.`);
  }
  if (!response.ok) {
    let payload: unknown;
    try { payload = await response.json(); } catch { payload = undefined; }
    throw new ApiError(response.status, detailMessage(payload, response.statusText), payload);
  }
  return response.json() as Promise<T>;
}

export function inspectionImageUrl(id: number, evidence = false): string {
  return `${API_BASE_URL}/inspection/${id}/${evidence ? 'evidence-image' : 'image'}`;
}
export function reportUrl(id: number): string { return `${API_BASE_URL}/report/${id}`; }
export function exportUrl(format: 'csv' | 'json'): string { return `${API_BASE_URL}/exports/history.${format}`; }

export async function inspectLabel(image: File, packageScope: PackageScope, commodityCategory: string): Promise<Inspection> {
  const body = new FormData();
  body.append('image', image);
  body.append('package_scope', packageScope);
  if (commodityCategory.trim()) body.append('commodity_category', commodityCategory.trim());
  return request<Inspection>('/inspect', { method: 'POST', body });
}
export function getInspection(id: number): Promise<Inspection> { return request(`/inspection/${id}`); }
export function getRules(): Promise<RuleInfo[]> { return request('/rules'); }
export function getAnalytics(): Promise<Analytics> { return request('/analytics'); }
export function getSystemStatus(): Promise<SystemStatus> { return request('/system/status'); }
export function getReviewQueue(limit = 100): Promise<HistoryItem[]> { return request(`/review-queue?limit=${limit}`); }

export function getHistory(filters: { limit?: number; status?: string; review_status?: string; search?: string; created_from?: string; created_to?: string } = {}): Promise<HistoryItem[]> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries({ limit: 100, ...filters })) {
    if (value !== undefined && value !== '') params.set(key, String(value));
  }
  return request(`/history?${params}`);
}

export function submitReview(id: number, review_status: ReviewStatus, reviewed_by: string, review_notes: string): Promise<{ status: string }> {
  return request(`/inspection/${id}/review`, {
    method: 'POST', body: JSON.stringify({ review_status, reviewed_by, review_notes: review_notes || null }),
  });
}

export function submitCorrection(id: number, field: string, corrected_text: string, reason: string, actor: string): Promise<Inspection> {
  return request(`/inspection/${id}/correct`, {
    method: 'POST', body: JSON.stringify({ field, corrected_text, reason, actor }),
  });
}
