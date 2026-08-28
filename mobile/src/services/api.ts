import { authStorage } from './authStorage';
import { Platform } from 'react-native';

// Network host configurations
export const PC_LAN_API_HOST = 'http://192.168.1.5:8000'; // Physical Android device over Wi-Fi
export const EMULATOR_API_HOST = 'http://10.0.2.2:8000';   // Android Emulator loopback
export const LOCALHOST_API_HOST = 'http://127.0.0.1:8000';  // Web / iOS simulator

// Default active API host for standalone build on physical Android phone
export const DEFAULT_API_HOST = Platform.OS === 'android' ? PC_LAN_API_HOST : LOCALHOST_API_HOST;

let customBaseUrl: string | null = null;

export const setApiBaseUrl = (url: string) => {
  customBaseUrl = url.replace(/\/$/, '');
};

export const getApiBaseUrl = () => {
  return customBaseUrl || DEFAULT_API_HOST;
};

export async function apiRequest<T = any>(
  endpoint: string,
  options: {
    method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
    body?: any;
    headers?: Record<string, string>;
    isFormData?: boolean;
  } = {}
): Promise<T> {
  const token = await authStorage.getToken();
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}${endpoint}`;

  const headers: Record<string, string> = {
    ...(options.isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  let body = options.body;
  if (body && !options.isFormData && typeof body !== 'string') {
    body = JSON.stringify(body);
  }

  const response = await fetch(url, {
    method: options.method || 'GET',
    headers,
    body,
  });

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
}

export const api = {
  // Auth
  login: (credentials: { officer_id: string; password: string }) =>
    apiRequest('/api/auth/login', { method: 'POST', body: credentials }),
  getProfile: () => apiRequest('/api/auth/me'),

  // Dashboard
  getDashboard: () => apiRequest('/api/dashboard'),

  // Inspections
  createInspection: (data: {
    product_name: string;
    category: string;
    brand_name?: string;
    location: string;
    batch_number?: string;
    notes?: string;
  }) => apiRequest('/api/inspections', { method: 'POST', body: data }),
  getInspection: (id: string) => apiRequest(`/api/inspections/${id}`),
  listInspections: () => apiRequest('/api/inspections'),
  getRecentInspections: () => apiRequest('/api/inspections/recent'),

  // Images & Quality
  uploadImage: (inspectionId: string, formData: FormData) =>
    apiRequest(`/api/inspections/${inspectionId}/images`, {
      method: 'POST',
      body: formData,
      isFormData: true,
    }),
  getInspectionImages: (inspectionId: string) => apiRequest(`/api/inspections/${inspectionId}/images`),

  // OCR & Declarations
  runOCR: (inspectionId: string) =>
    apiRequest(`/api/inspections/${inspectionId}/ocr`, { method: 'POST' }),
  getDeclarations: (inspectionId: string) =>
    apiRequest(`/api/inspections/${inspectionId}/declarations`),
  updateDeclaration: (
    declarationId: string,
    data: { corrected_value?: string; verification_status?: string; correction_reason?: string }
  ) => apiRequest(`/api/declarations/${declarationId}`, { method: 'PATCH', body: data }),

  // Rule Engine & Adjudication
  evaluateRules: (inspectionId: string) =>
    apiRequest(`/api/inspections/${inspectionId}/evaluate`, { method: 'POST' }),
  getFindings: (inspectionId: string) =>
    apiRequest(`/api/inspections/${inspectionId}/findings`),
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
  getReportMetadata: (inspectionId: string) =>
    apiRequest(`/api/inspections/${inspectionId}/report`),
  generateReport: (inspectionId: string) =>
    apiRequest(`/api/inspections/${inspectionId}/report`, { method: 'POST' }),
  getReportsList: () => apiRequest('/api/reports'),
  getAuditLogs: (inspectionId: string) => apiRequest(`/api/inspections/${inspectionId}/audit-logs`),
};
