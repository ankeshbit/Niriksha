import { authStorage } from './authStorage';
import { Platform } from 'react-native';

// Network host configurations
export const EMULATOR_API_HOST = 'http://10.0.2.2:8000';   // Android Emulator loopback
export const LOCALHOST_API_HOST = 'http://127.0.0.1:8000';  // Web / iOS simulator
export const PRODUCTION_API_HOST = 'https://niriksha-1.onrender.com'; // Live Render Backend

// Environment-configured API host (configured via EXPO_PUBLIC_API_URL in .env or EAS build)
const expoEnvUrl = (process.env as Record<string, string | undefined>)?.EXPO_PUBLIC_API_URL;
const ENV_API_HOST = expoEnvUrl ? expoEnvUrl.replace(/\/$/, '') : null;

// Default active API host:
// - Always default to PRODUCTION_API_HOST (Render backend) on production APKs unless explicitly configured
export const DEFAULT_API_HOST = ENV_API_HOST || PRODUCTION_API_HOST;

let customBaseUrl: string | null = null;

export const setApiBaseUrl = (url: string) => {
  customBaseUrl = url.replace(/\/$/, '');
};

export const getApiBaseUrl = () => {
  if (customBaseUrl) return customBaseUrl;

  // On Web: ALWAYS dynamically match current window hostname to prevent origin/port mismatch
  if (Platform.OS === 'web' && typeof window !== 'undefined' && window.location?.hostname) {
    const host = window.location.hostname;
    if (host && host !== 'localhost' && host !== '127.0.0.1') {
      return `https://${host}`;
    }
  }

  if (ENV_API_HOST) return ENV_API_HOST;

  return PRODUCTION_API_HOST;
};

// ─── Error classification ─────────────────────────────────────────────────────

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
 * FIX-RC-4: Separates client-side blob: URI errors from genuine network failures.
 * A blob: fetch error is NOT a connectivity problem and must not trigger offline mode.
 */
export function classifyFetchError(err: any, url?: string): ClassifiedError {
  const msg = String(err?.message || err || '');
  const isAbort = err?.name === 'AbortError' || msg.includes('aborted');
  const isNetworkMsg =
    msg.includes('Failed to fetch') ||
    msg.includes('Network request failed') ||
    msg.includes('NetworkError') ||
    msg.includes('ECONNREFUSED') ||
    msg.includes('ENOTFOUND');

  // Client-side blob URL fetch failure (RC-3/RC-4) — NOT a network/connectivity error
  if (url && (url.startsWith('blob:') || url.startsWith('data:'))) {
    return {
      type: 'BLOB_FETCH_ERROR',
      message: msg,
      userMessage:
        'Could not read the selected image file. Please select the image again.',
    };
  }

  if (isAbort) {
    return {
      type: 'REQUEST_TIMEOUT',
      message: msg,
      userMessage:
        'The request took too long. The server may be processing a complex task. Please try again.',
    };
  }

  if (isNetworkMsg) {
    return {
      type: 'NETWORK_UNREACHABLE',
      message: msg,
      userMessage:
        'Backend connection unavailable. Your draft is safely stored locally.',
    };
  }

  const status = err?.status ?? err?.statusCode;
  if (status === 401 || status === 403) {
    return {
      type: 'AUTH_ERROR',
      status,
      message: msg,
      userMessage: status === 401 ? 'Session expired. Please sign in again.' : 'Access denied.',
    };
  }

  if (status && status >= 500) {
    return {
      type: 'SERVER_ERROR',
      status,
      message: msg,
      userMessage: 'Server error. Please try again in a moment.',
    };
  }

  if (status) {
    return {
      type: 'HTTP_ERROR',
      status,
      message: msg,
      userMessage: msg || `Request failed (${status})`,
    };
  }

  return {
    type: 'UNKNOWN_ERROR',
    message: msg,
    userMessage: msg || 'An unexpected error occurred.',
  };
}

/**
 * Returns true if the classified error represents a genuine network connectivity
 * failure that justifies switching to offline draft mode.
 *
 * Critically, BLOB_FETCH_ERROR and REQUEST_TIMEOUT are NOT connectivity failures.
 */
export function isConnectivityError(classified: ClassifiedError): boolean {
  return classified.type === 'NETWORK_UNREACHABLE';
}

// ─── Core API request function ────────────────────────────────────────────────

/**
 * FIX-RC-5: Added `timeoutMs` option to `apiRequest`.
 *
 * Default timeout: 30000ms (30s) — covers normal API calls.
 * OCR endpoint should use 180000ms (3 minutes) for CPU-heavy PaddleOCR.
 *
 * The AbortController fires after `timeoutMs`. The error thrown is classified as
 * REQUEST_TIMEOUT (not NETWORK_UNREACHABLE), so callers can decide appropriately.
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
      throw new Error('Session expired. Please sign in again.');
    }

    if (!response.ok) {
      let errorDetail = `Request failed (${response.status})`;
      try {
        const errJson = await response.json();
        if (errJson.detail) {
          errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
        }
      } catch {
        // Use fallback error
      }
      throw new Error(errorDetail);
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
    throw err;
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
