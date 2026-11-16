import { authStorage } from './authStorage';
import { Platform } from 'react-native';
import Constants from 'expo-constants';

// Network host configurations
export const EMULATOR_API_HOST = 'http://10.0.2.2:8000';   // Android Emulator loopback
export const LOCALHOST_API_HOST = 'http://127.0.0.1:8000';  // Web / iOS simulator
export const PRODUCTION_API_HOST = 'https://niriksha-1.onrender.com'; // Live Render Backend

let customBaseUrl: string | null = null;

export const setApiBaseUrl = (url: string) => {
  customBaseUrl = url.replace(/\/$/, '');
};

/**
 * Resolves local development API host:
 * 1. Inspects Expo Metro debugger/manifest host to auto-detect the host machine's LAN IP
 *    (seamlessly connects physical devices and Expo Go over Wi-Fi without hardcoded IPs).
 * 2. On Android emulator: uses standard emulator loopback 10.0.2.2:8000 when direct host resolution is unavailable.
 * 3. On Web / iOS simulator: uses 127.0.0.1:8000 or current browser origin.
 */
export function resolveDevelopmentHost(): string {
  // Try modern Expo config hostUri or legacy debuggerHost
  const hostUri =
    Constants.expoConfig?.hostUri ||
    (Constants as any).manifest2?.extra?.expoClient?.hostUri ||
    (Constants as any).manifest?.debuggerHost;

  if (hostUri && typeof hostUri === 'string') {
    const ip = hostUri.split(':')[0];
    if (ip && ip !== 'localhost' && ip !== '127.0.0.1') {
      return `http://${ip}:8000`;
    }
  }

  // Fallback to platform-specific localhost alias
  if (Platform.OS === 'android') {
    return EMULATOR_API_HOST;
  }

  if (Platform.OS === 'web' && typeof window !== 'undefined' && window.location?.hostname) {
    const host = window.location.hostname;
    if (host && host !== 'localhost' && host !== '127.0.0.1') {
      return `http://${host}:8000`;
    }
  }

  return LOCALHOST_API_HOST;
}

/**
 * Authoritative API base URL resolution:
 * 1. Runtime override via setApiBaseUrl(url)
 * 2. Explicit environment variable EXPO_PUBLIC_API_URL (takes precedence in all environments)
 * 3. Development fallback (__DEV__): dynamically inferred Metro host or platform loopback
 * 4. Production Web deployment fallback (matching custom origin)
 * 5. Production APK / bundle default (Render hosted backend)
 */
export const getApiBaseUrl = (): string => {
  if (customBaseUrl) return customBaseUrl;

  const expoEnvUrl = (process.env as Record<string, string | undefined>)?.EXPO_PUBLIC_API_URL;
  if (expoEnvUrl && expoEnvUrl.trim()) {
    return expoEnvUrl.trim().replace(/\/$/, '');
  }

  const isDev = typeof __DEV__ !== 'undefined' ? __DEV__ : process.env.NODE_ENV !== 'production';
  if (isDev) {
    return resolveDevelopmentHost();
  }

  // On Web: dynamically match current window hostname if on custom deployment without EXPO_PUBLIC_API_URL
  if (Platform.OS === 'web' && typeof window !== 'undefined' && window.location?.hostname) {
    const host = window.location.hostname;
    if (host && host !== 'localhost' && host !== '127.0.0.1') {
      const proto = window.location.protocol || 'https:';
      return `${proto}//${host}`;
    }
  }

  return PRODUCTION_API_HOST;
};

// Backwards-compatible default constant
export const DEFAULT_API_HOST = getApiBaseUrl();

// ─── Error Sanitization & Classification ─────────────────────────────────────

/**
 * Strips sensitive data (JWTs, auth headers, database credentials, server stack traces)
 * from error messages before they reach the UI.
 */
export function sanitizeErrorMessage(message: string): string {
  if (!message || typeof message !== 'string') return 'An error occurred';
  return message
    // Redact JWT tokens
    .replace(/eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g, '[REDACTED_TOKEN]')
    // Redact Bearer tokens
    .replace(/Bearer\s+[A-Za-z0-9_\-\.]{15,}/gi, 'Bearer [REDACTED]')
    // Redact DB connection strings
    .replace(/(?:postgres(?:ql)?(?:\+psycopg)?|mysql|mongodb):\/\/[^@\s]+@[^\s]+/gi, '[REDACTED_DATABASE_URL]')
    // Redact internal password keys
    .replace(/password(?:_hash)?["']?\s*[:=]\s*["']?[^"'\s,]+/gi, 'password=[REDACTED]')
    // Replace unhandled python stack traces
    .replace(/Traceback \(most recent call last\)[\s\S]+/g, 'Internal server error occurred.');
}

export type ApiErrorKind =
  | 'AUTHENTICATION'      // 401
  | 'AUTHORIZATION'       // 403
  | 'NOT_FOUND'           // 404
  | 'VALIDATION'          // 400, 422
  | 'CONFLICT'            // 409
  | 'RATE_LIMIT'          // 429
  | 'SERVER_ERROR'        // 5xx
  | 'NETWORK_UNREACHABLE' // genuine network drop
  | 'REQUEST_TIMEOUT'     // AbortError / timeout
  | 'BLOB_FETCH_ERROR'    // client blob reading error
  | 'UNKNOWN';

export interface ApiErrorOptions {
  message: string;
  status?: number;
  kind?: ApiErrorKind;
  data?: any;
  url?: string;
  cause?: any;
  userMessage?: string;
}

/**
 * Authoritative, strongly-typed API error structure.
 * Preserves HTTP status code, server response body, URL, and category,
 * while preventing sensitive token/internal leaks.
 */
export class ApiError extends Error {
  public readonly status?: number;
  public readonly statusCode?: number;
  public readonly kind: ApiErrorKind;
  public readonly data?: any;
  public readonly url?: string;
  public readonly targetUrl?: string;
  public readonly response?: { status: number; data?: any };
  public readonly isNetworkError: boolean;
  public readonly userMessage: string;

  constructor(options: ApiErrorOptions) {
    const cleanMsg = sanitizeErrorMessage(options.message);
    super(cleanMsg);
    this.name = 'ApiError';
    this.status = options.status;
    this.statusCode = options.status;
    this.data = options.data;
    this.url = options.url;
    this.targetUrl = options.url;
    if (options.cause) {
      this.cause = options.cause;
    }

    if (options.status !== undefined) {
      this.response = {
        status: options.status,
        data: options.data,
      };
    }

    if (options.kind) {
      this.kind = options.kind;
    } else if (options.status === 401) {
      this.kind = 'AUTHENTICATION';
    } else if (options.status === 403) {
      this.kind = 'AUTHORIZATION';
    } else if (options.status === 404) {
      this.kind = 'NOT_FOUND';
    } else if (options.status === 400 || options.status === 422) {
      this.kind = 'VALIDATION';
    } else if (options.status === 409) {
      this.kind = 'CONFLICT';
    } else if (options.status === 429) {
      this.kind = 'RATE_LIMIT';
    } else if (options.status && options.status >= 500) {
      this.kind = 'SERVER_ERROR';
    } else {
      this.kind = 'UNKNOWN';
    }

    this.isNetworkError = this.kind === 'NETWORK_UNREACHABLE';

    if (options.userMessage) {
      this.userMessage = sanitizeErrorMessage(options.userMessage);
    } else if (this.kind === 'AUTHENTICATION') {
      this.userMessage = 'Session expired. Please sign in again.';
    } else if (this.kind === 'AUTHORIZATION') {
      this.userMessage = 'Access denied. You do not have permission to perform this action.';
    } else if (this.kind === 'NOT_FOUND') {
      this.userMessage = 'The requested resource was not found.';
    } else if (this.kind === 'RATE_LIMIT') {
      this.userMessage = 'Too many requests. Please slow down and try again.';
    } else if (this.kind === 'SERVER_ERROR') {
      this.userMessage = 'Server error. Please try again in a moment.';
    } else if (this.kind === 'NETWORK_UNREACHABLE') {
      this.userMessage = 'Backend connection unavailable. Your draft is safely stored locally.';
    } else if (this.kind === 'REQUEST_TIMEOUT') {
      this.userMessage = 'The request took too long. The server may be processing a complex task. Please try again.';
    } else if (this.kind === 'BLOB_FETCH_ERROR') {
      this.userMessage = 'Could not read the selected image file. Please select the image again.';
    } else {
      this.userMessage = cleanMsg || 'An unexpected error occurred.';
    }

    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

export type FetchErrorType =
  | 'NETWORK_UNREACHABLE'
  | 'REQUEST_TIMEOUT'
  | 'HTTP_ERROR'
  | 'AUTH_ERROR'
  | 'SERVER_ERROR'
  | 'BLOB_FETCH_ERROR'
  | 'UNKNOWN_ERROR';

export interface ClassifiedError {
  type: FetchErrorType;
  status?: number;
  message: string;
  userMessage: string;
}

/**
 * Classifies a fetch/network error into a structured type so callers can make
 * informed decisions (e.g. offline draft vs user error vs retry).
 *
 * Guaranteed invariants:
 * - Server errors (5xx) and HTTP errors (4xx) preserve their status code.
 * - Server errors are NEVER misclassified as offline/connectivity failures.
 * - Timeouts and blob reading errors are NEVER misclassified as connectivity failures.
 */
export function classifyFetchError(err: any, url?: string): ClassifiedError {
  const msg = String(err?.message || err || '');
  const targetUrl = url || err?.url || err?.targetUrl;

  // 1. Client-side blob URL fetch failure — NOT a network/connectivity error
  if ((targetUrl && (targetUrl.startsWith('blob:') || targetUrl.startsWith('data:'))) || err?.kind === 'BLOB_FETCH_ERROR') {
    return {
      type: 'BLOB_FETCH_ERROR',
      message: sanitizeErrorMessage(msg),
      userMessage: 'Could not read the selected image file. Please select the image again.',
    };
  }

  // 2. Timeout
  const isAbort = err?.name === 'AbortError' || err?.kind === 'REQUEST_TIMEOUT' || msg.includes('aborted');
  if (isAbort) {
    return {
      type: 'REQUEST_TIMEOUT',
      message: sanitizeErrorMessage(msg),
      userMessage: 'The request took too long. The server may be processing a complex task. Please try again.',
    };
  }

  // 3. Status checks (MUST take precedence over message strings to prevent 500/502 from being classed as offline)
  const status = err?.status ?? err?.statusCode ?? err?.response?.status;

  if (status === 401 || status === 403 || err?.kind === 'AUTHENTICATION' || err?.kind === 'AUTHORIZATION') {
    return {
      type: 'AUTH_ERROR',
      status: status || (err?.kind === 'AUTHENTICATION' ? 401 : 403),
      message: sanitizeErrorMessage(msg),
      userMessage: (status === 401 || err?.kind === 'AUTHENTICATION')
        ? 'Session expired. Please sign in again.'
        : 'Access denied.',
    };
  }

  if ((status && status >= 500) || err?.kind === 'SERVER_ERROR') {
    return {
      type: 'SERVER_ERROR',
      status: status || 500,
      message: sanitizeErrorMessage(msg),
      userMessage: 'Server error. Please try again in a moment.',
    };
  }

  if (status) {
    return {
      type: 'HTTP_ERROR',
      status,
      message: sanitizeErrorMessage(msg),
      userMessage: sanitizeErrorMessage(msg) || `Request failed (${status})`,
    };
  }

  // 4. Genuine network connectivity failure without HTTP status
  const isNetworkMsg =
    err?.kind === 'NETWORK_UNREACHABLE' ||
    msg.includes('Failed to fetch') ||
    msg.includes('Network request failed') ||
    msg.includes('NetworkError') ||
    msg.includes('ECONNREFUSED') ||
    msg.includes('ENOTFOUND');

  if (isNetworkMsg) {
    const targetDesc = targetUrl ? ` (${targetUrl})` : '';
    return {
      type: 'NETWORK_UNREACHABLE',
      message: sanitizeErrorMessage(`${msg}${targetDesc}`),
      userMessage: `Backend connection unavailable${targetDesc}. Your draft is safely stored locally.`,
    };
  }

  return {
    type: 'UNKNOWN_ERROR',
    message: sanitizeErrorMessage(msg),
    userMessage: sanitizeErrorMessage(msg) || 'An unexpected error occurred.',
  };
}

/**
 * Returns true if the classified error represents a genuine network connectivity
 * failure that justifies switching to offline draft mode.
 *
 * Critically, BLOB_FETCH_ERROR, REQUEST_TIMEOUT, and SERVER_ERROR are NOT connectivity failures.
 */
export function isConnectivityError(classified: ClassifiedError): boolean {
  return classified.type === 'NETWORK_UNREACHABLE';
}

// ─── Core API request function ────────────────────────────────────────────────

/**
 * Authoritative API request function:
 * - Preserves HTTP status codes via typed ApiError instances.
 * - Handles 401 session expiry and token clearing.
 * - Distinguishes timeouts, server errors, and network disconnects.
 * - Preserves multipart form data uploads.
 */
export async function apiRequest<T = any>(
  endpoint: string,
  options: {
    method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
    body?: any;
    headers?: Record<string, string>;
    isFormData?: boolean;
    /** Request timeout in milliseconds. Default: 30000ms. Use 180000ms for OCR. */
    timeoutMs?: number;
    /** Optional external AbortSignal for user cancellation */
    signal?: AbortSignal;
  } = {}
): Promise<T> {
  const effectiveMethod = options.method || 'GET';
  const token = await authStorage.getToken();
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}${endpoint}`;
  const timeoutMs = options.timeoutMs ?? 30000;

  const headers: Record<string, string> = {
    ...(options.isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  let body = options.body;
  if (body && !options.isFormData && typeof body !== 'string') {
    body = JSON.stringify(body);
  }

  // Set up request timeout via AbortController
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const timeoutId = controller
    ? setTimeout(() => controller.abort(), timeoutMs)
    : null;

  if (controller && options.signal) {
    if (options.signal.aborted) {
      controller.abort();
    } else {
      options.signal.addEventListener('abort', () => controller.abort(), { once: true });
    }
  }

  try {
    const response = await fetch(url, {
      method: effectiveMethod,
      headers,
      body,
      signal: controller ? controller.signal : undefined,
    });

    if (timeoutId) clearTimeout(timeoutId);

    if (response.status === 401) {
      await authStorage.clear();
      throw new ApiError({
        message: 'Session expired. Please sign in again.',
        status: 401,
        kind: 'AUTHENTICATION',
        url,
        userMessage: 'Session expired. Please sign in again.',
      });
    }

    if (!response.ok) {
      let errorDetail = `Request failed (${response.status})`;
      let responseData: any = undefined;
      try {
        responseData = await response.json();
        if (responseData && responseData.detail) {
          errorDetail = typeof responseData.detail === 'string'
            ? responseData.detail
            : JSON.stringify(responseData.detail);
        }
      } catch {
        try {
          const text = await response.text();
          if (text) errorDetail = text;
        } catch {}
      }

      throw new ApiError({
        message: errorDetail,
        status: response.status,
        data: responseData,
        url,
      });
    }

    // Handle empty responses or 204 No Content
    if (response.status === 204) {
      return {} as T;
    }

    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return await response.json();
    }

    return (await response.text()) as unknown as T;
  } catch (err: any) {
    if (timeoutId) clearTimeout(timeoutId);

    // If it is already an ApiError (e.g. from non-ok HTTP response or 401), re-throw
    if (err instanceof ApiError) {
      throw err;
    }

    const msg = String(err?.message || err || '');
    const isAbort = err?.name === 'AbortError' || msg.includes('aborted');
    const isNetworkMsg =
      msg.includes('Failed to fetch') ||
      msg.includes('Network request failed') ||
      msg.includes('NetworkError') ||
      msg.includes('ECONNREFUSED') ||
      msg.includes('ENOTFOUND');

    if (isAbort) {
      throw new ApiError({
        message: 'Request timed out. Please try again.',
        kind: 'REQUEST_TIMEOUT',
        url,
        cause: err,
        userMessage: 'The request took too long. The server may be processing a complex task. Please try again.',
      });
    }

    if (isNetworkMsg) {
      throw new ApiError({
        message: `Backend connection unavailable (${url})`,
        kind: 'NETWORK_UNREACHABLE',
        url,
        cause: err,
        userMessage: 'Backend connection unavailable. Your draft is safely stored locally.',
      });
    }

    throw new ApiError({
      message: msg || 'An unexpected error occurred.',
      kind: 'UNKNOWN',
      url,
      cause: err,
      userMessage: msg || 'An unexpected error occurred.',
    });
  }
}

export const api = {
  // Auth (timeoutMs: 60000 allows Render free-tier instance wake-up without premature abort)
  login: (credentials: { officer_id: string; password: string }) =>
    apiRequest('/api/auth/login', { method: 'POST', body: credentials, timeoutMs: 60000 }),
  logout: () => apiRequest('/api/auth/logout', { method: 'POST' }),
  getProfile: () => apiRequest('/api/auth/me'),
  updateProfile: (data: { email?: string; phone?: string }) =>
    apiRequest('/api/auth/me', { method: 'PATCH', body: data }),
  changePassword: (data: { current_password: string; new_password: string }) =>
    apiRequest('/api/auth/change-password', { method: 'POST', body: data }),

  // Dashboard
  getDashboard: () => apiRequest('/api/dashboard'),
  getDashboardSummary: () => apiRequest('/api/dashboard/summary'),
  getDashboardInspections: (params?: {
    status?: string;
    overall_status?: string;
    start_date?: string;
    end_date?: string;
    category?: string;
    location?: string;
    inspector_id?: string;
    has_report?: boolean;
    search?: string;
    limit?: number;
    offset?: number;
  }) => {
    let query = '';
    if (params) {
      const cleanParams: Record<string, string> = {};
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') {
          cleanParams[k] = String(v);
        }
      });
      const q = new URLSearchParams(cleanParams).toString();
      if (q) query = '?' + q;
    }
    return apiRequest(`/api/dashboard/inspections${query}`);
  },
  getDashboardPendingActions: (limit?: number) => {
    const q = limit ? `?limit=${limit}` : '';
    return apiRequest(`/api/dashboard/pending-actions${q}`);
  },

  // Health & Connectivity
  checkHealth: () => apiRequest('/api/health'),

  // Inspections
  createInspection: (data: {
    product_name: string;
    category: string;
    brand_name?: string;
    location: string;
    batch_number?: string;
    notes?: string;
    client_draft_id?: string;
    inspection_type?: string;
  }) => apiRequest('/api/inspections', { method: 'POST', body: data }),
  getInspection: (id: string) => apiRequest(`/api/inspections/${id}`),
  listInspections: (params?: { status?: string; limit?: number; offset?: number }) => {
    let query = '';
    if (params) {
      const q = new URLSearchParams(params as any).toString();
      if (q) query = '?' + q;
    }
    return apiRequest(`/api/inspections${query}`);
  },
  getRecentInspections: () => apiRequest('/api/inspections/recent'),

  // Images & Quality
  uploadImage: (inspectionId: string, formData: FormData) =>
    apiRequest(`/api/inspections/${inspectionId}/images`, {
      method: 'POST',
      body: formData,
      isFormData: true,
      timeoutMs: 60000,  // 60s for image upload
    }),
  checkImageQuality: (formData: FormData) =>
    apiRequest('/api/quality-check', {
      method: 'POST',
      body: formData,
      isFormData: true,
      timeoutMs: 30000,
    }),
  getInspectionImages: (inspectionId: string) => apiRequest(`/api/inspections/${inspectionId}/images`),
  deleteImage: (imageId: string) =>
    apiRequest(`/api/images/${imageId}`, { method: 'DELETE' }),
  deleteImageBySlot: (inspectionId: string, viewType: string) =>
    apiRequest(`/api/inspections/${inspectionId}/images/slot/${viewType}`, { method: 'DELETE' }),

  // OCR & Declarations
  /**
   * Durable Asynchronous OCR Job: Start processing.
   * Returns immediately (<100ms) with { job_id, inspection_id, status: "PENDING" }.
   */
  startOCRJob: (inspectionId: string, options?: { force?: boolean; signal?: AbortSignal }) =>
    apiRequest(`/api/inspections/${inspectionId}/ocr/start${options?.force ? '?force=true' : ''}`, {
      method: 'POST',
      timeoutMs: 15000,
      signal: options?.signal,
    }),

  /**
   * Durable Asynchronous OCR Job: Poll job status.
   * Retrieves active stage, progress, elapsed time, and completion state.
   */
  getOCRJobStatus: (inspectionId: string, options?: { signal?: AbortSignal }) =>
    apiRequest(`/api/inspections/${inspectionId}/ocr/status`, {
      method: 'GET',
      timeoutMs: 10000,
      signal: options?.signal,
    }),

  /**
   * Run OCR endpoint (legacy synchronous compatibility).
   * Supports optional AbortSignal for user cancellation.
   */
  runOCR: (inspectionId: string, options?: { signal?: AbortSignal }) =>
    apiRequest(`/api/inspections/${inspectionId}/ocr`, {
      method: 'POST',
      timeoutMs: 600000,
      signal: options?.signal,
    }),
  getDeclarations: (inspectionId: string) =>
    apiRequest(`/api/inspections/${inspectionId}/declarations`),
  getBarcodes: (inspectionId: string) =>
    apiRequest(`/api/inspections/${inspectionId}/barcodes`),
  updateDeclaration: (
    declarationId: string,
    data: { corrected_value?: string; verification_status?: string; correction_reason?: string }
  ) => apiRequest(`/api/declarations/${declarationId}`, { method: 'PATCH', body: data }),

  // Rule Engine & Adjudication
  evaluateRules: (inspectionId: string) =>
    apiRequest(`/api/inspections/${inspectionId}/evaluate`, { method: 'POST' }),
  getFindings: (inspectionId: string, params?: { status?: string }) => {
    const q = params?.status ? `?status=${encodeURIComponent(params.status)}` : '';
    return apiRequest(`/api/inspections/${inspectionId}/findings${q}`);
  },
  getFinding: (findingId: string) => apiRequest(`/api/findings/${findingId}`),
  adjudicateFinding: (
    findingId: string,
    data: {
      action: 'CONFIRMED' | 'DISMISSED' | 'NEEDS_MORE_EVIDENCE' | 'NOT_APPLICABLE' | 'CORRECTED';
      notes?: string;
      corrected_value?: string;
    }
  ) => apiRequest(`/api/findings/${findingId}/adjudicate`, { method: 'PATCH', body: data }),
  requestNewImage: (findingId: string) =>
    apiRequest(`/api/findings/${findingId}/request-new-image`, { method: 'POST' }),
  getFindingEvidence: (findingId: string) => apiRequest(`/api/findings/${findingId}/evidence`),


  // Report & Finalization
  finalizeInspection: (inspectionId: string, data: { officer_notes?: string; final_status?: string }) =>
    apiRequest(`/api/inspections/${inspectionId}/finalize`, { method: 'POST', body: data }),
  getReportEligibility: (inspectionId: string) =>
    apiRequest(`/api/inspections/${inspectionId}/report/eligibility`),
  getReportMetadata: (inspectionId: string) =>
    apiRequest(`/api/inspections/${inspectionId}/report`),
  generateReport: (inspectionId: string) =>
    apiRequest(`/api/inspections/${inspectionId}/report`, { method: 'POST' }),
  getReportsList: () => apiRequest('/api/reports'),
  getReportById: (reportId: string) => apiRequest(`/api/reports/${reportId}`),
  getInspectionReportDocxUrl: (inspectionId: string) =>
    `${getApiBaseUrl()}/api/inspections/${inspectionId}/report/docx`,
  getReportDocxUrl: (reportId: string) =>
    `${getApiBaseUrl()}/api/reports/${reportId}/docx`,
  getAuditLogs: (inspectionId: string) => apiRequest(`/api/inspections/${inspectionId}/audit-logs`),

  // Product Listing & Online Compliance (PS 26034)
  saveProductListing: (inspectionId: string, data: any) =>
    apiRequest(`/api/inspections/${inspectionId}/listing`, { method: 'POST', body: data }),
  getProductListing: (inspectionId: string) =>
    apiRequest(`/api/inspections/${inspectionId}/listing`),
  compareProductListing: (inspectionId: string) =>
    apiRequest(`/api/inspections/${inspectionId}/listing/compare`, { method: 'POST' }),
  getListingComparison: (inspectionId: string) =>
    apiRequest(`/api/inspections/${inspectionId}/listing/comparison`),
  adjudicateListingComparison: (
    inspectionId: string,
    comparisonId: string,
    data: { status: 'VERIFIED_MATCH' | 'CONFIRMED_DISCREPANCY' | 'DISMISSED_DISCREPANCY'; remarks?: string }
  ) =>
    apiRequest(`/api/inspections/${inspectionId}/listing/comparisons/${comparisonId}/adjudicate`, {
      method: 'POST',
      body: data,
    }),

  // Declaration Validation Matrix & Compliance Summary (SIH PS 26034)
  getDeclarationValidation: (inspectionId: string) =>
    apiRequest(`/api/inspections/${inspectionId}/declaration-validation`),
  getComplianceSummary: (inspectionId: string, params?: { status?: string }) => {
    const q = params?.status ? `?status=${encodeURIComponent(params.status)}` : '';
    return apiRequest(`/api/inspections/${inspectionId}/compliance-summary${q}`);
  },

  // Search, Retrieval & Product Repository (SIH PS 26034)
  searchInspections: (params?: {
    search?: string;
    status?: string;
    overall_status?: string;
    start_date?: string;
    end_date?: string;
    category?: string;
    location?: string;
    finding_type?: string;
    has_report?: boolean;
    page?: number;
    page_size?: number;
  }) => {
    let query = '';
    if (params) {
      const cleanParams: Record<string, string> = {};
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && String(v).trim() !== '') {
          cleanParams[k] = String(v);
        }
      });
      const q = new URLSearchParams(cleanParams).toString();
      if (q) query = '?' + q;
    }
    return apiRequest(`/api/inspections/search${query}`);
  },
  searchProducts: (params?: {
    search?: string;
    category?: string;
    compliance_status?: string;
    page?: number;
    page_size?: number;
  }) => {
    let query = '';
    if (params) {
      const cleanParams: Record<string, string> = {};
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && String(v).trim() !== '') {
          cleanParams[k] = String(v);
        }
      });
      const q = new URLSearchParams(cleanParams).toString();
      if (q) query = '?' + q;
    }
    return apiRequest(`/api/products/search${query}`);
  },
  getProductHistory: (productKey: string, params?: { page?: number; page_size?: number }) => {
    let query = '';
    if (params) {
      const cleanParams: Record<string, string> = {};
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && String(v).trim() !== '') {
          cleanParams[k] = String(v);
        }
      });
      const q = new URLSearchParams(cleanParams).toString();
      if (q) query = '?' + q;
    }
    return apiRequest(`/api/products/${encodeURIComponent(productKey)}/history${query}`);
  },

  // Supervisor Management Endpoints
  getSupervisorDashboard: () => apiRequest('/api/supervisor/dashboard'),
  getSupervisorInspectors: () => apiRequest('/api/supervisor/inspectors'),
  getSupervisorInspections: (params?: {
    page?: number;
    page_size?: number;
    search?: string;
    inspector_id?: string;
    status?: string;
    overall_status?: string;
    category?: string;
    has_report?: boolean;
    date_from?: string;
    date_to?: string;
    sort_by?: string;
    sort_order?: string;
  }) => {
    let query = '';
    if (params) {
      const cleanParams: Record<string, string> = {};
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && String(v).trim() !== '') {
          cleanParams[k] = String(v);
        }
      });
      const q = new URLSearchParams(cleanParams).toString();
      if (q) query = '?' + q;
    }
    return apiRequest(`/api/supervisor/inspections${query}`);
  },
  deleteInspection: (inspectionId: string, confirmationInspectionNumber: string, reason?: string) =>
    apiRequest(`/api/inspections/${inspectionId}`, {
      method: 'DELETE',
      body: {
        confirmation_inspection_number: confirmationInspectionNumber,
        reason: reason || 'Supervisor administrative deletion',
      },
    }),
  deleteReport: (inspectionId: string) =>
    apiRequest(`/api/inspections/${inspectionId}/report`, {
      method: 'DELETE',
    }),
};
