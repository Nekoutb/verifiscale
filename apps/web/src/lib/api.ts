/**
 * Thin fetch wrapper around the FastAPI backend.
 * Reads the bearer token from localStorage; redirects to /login on 401.
 */

// Default to same-origin (empty prefix → relative URLs) when no env var is set.
// In dev with no proxy, fall back to the local API on port 8000.
const API_URL = process.env.NEXT_PUBLIC_API_URL
  ?? (typeof window === 'undefined' || window.location.port === '3000' ? 'http://localhost:8000' : '');
const TOKEN_KEY = 'fa_token';

export const getToken = (): string | null => {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(TOKEN_KEY);
};

export const setToken = (token: string | null): void => {
  if (typeof window === 'undefined') return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
};

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
  }
}

type RequestOptions = Omit<RequestInit, 'body'> & { body?: unknown; raw?: boolean };

export async function api<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers = new Headers(opts.headers || {});
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  let body: BodyInit | undefined;
  if (opts.body !== undefined) {
    if (opts.raw) {
      body = opts.body as BodyInit;
    } else {
      headers.set('Content-Type', 'application/json');
      body = JSON.stringify(opts.body);
    }
  }

  const res = await fetch(`${API_URL}${path}`, { ...opts, headers, body });

  if (res.status === 401 && typeof window !== 'undefined' && path !== '/auth/login') {
    setToken(null);
    if (window.location.pathname !== '/login') window.location.href = '/login';
    throw new ApiError(401, 'Session expirée');
  }

  if (!res.ok) {
    let detail: unknown;
    try { detail = await res.json(); } catch { /* ignore */ }
    const msg =
      (detail as { detail?: string })?.detail ||
      res.statusText ||
      `Erreur ${res.status}`;
    throw new ApiError(res.status, msg, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const apiUploadForm = <T = unknown>(path: string, form: FormData): Promise<T> =>
  api<T>(path, { method: 'POST', body: form, raw: true });
