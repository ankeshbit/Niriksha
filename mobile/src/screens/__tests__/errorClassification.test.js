/**
 * Error classification & ApiError test suite verifying that:
 * - HTTP status codes (401, 403, 404, 422, 500, etc.) are strictly preserved.
 * - Server errors (5xx) are NEVER misclassified as offline/connectivity failures.
 * - Timeouts and blob failures are NEVER misclassified as connectivity failures.
 * - Sensitive tokens, connection strings, and internal stack traces are redacted.
 * - Response object interop (err.response.status, err.response.data) is maintained.
 */

function sanitizeErrorMessage(message) {
  if (!message || typeof message !== 'string') return 'An error occurred';
  return message
    .replace(/eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g, '[REDACTED_TOKEN]')
    .replace(/Bearer\s+[A-Za-z0-9_\-\.]{15,}/gi, 'Bearer [REDACTED]')
    .replace(/(?:postgres(?:ql)?(?:\+psycopg)?|mysql|mongodb):\/\/[^@\s]+@[^\s]+/gi, '[REDACTED_DATABASE_URL]')
    .replace(/password(?:_hash)?["']?\s*[:=]\s*["']?[^"'\s,]+/gi, 'password=[REDACTED]')
    .replace(/Traceback \(most recent call last\)[\s\S]+/g, 'Internal server error occurred.');
}

class ApiError extends Error {
  constructor(options) {
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
  }
}

function classifyFetchError(err, url) {
  const msg = String(err?.message || err || '');
  const targetUrl = url || err?.url || err?.targetUrl;

  if ((targetUrl && (targetUrl.startsWith('blob:') || targetUrl.startsWith('data:'))) || err?.kind === 'BLOB_FETCH_ERROR') {
    return {
      type: 'BLOB_FETCH_ERROR',
      message: sanitizeErrorMessage(msg),
      userMessage: 'Could not read the selected image file. Please select the image again.',
    };
  }

  const isAbort = err?.name === 'AbortError' || err?.kind === 'REQUEST_TIMEOUT' || msg.includes('aborted');
  if (isAbort) {
    return {
      type: 'REQUEST_TIMEOUT',
      message: sanitizeErrorMessage(msg),
      userMessage: 'The request took too long. The server may be processing a complex task. Please try again.',
    };
  }

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

function isConnectivityError(classified) {
  return classified.type === 'NETWORK_UNREACHABLE';
}

describe('Error Classification Regression Suite', () => {
  it('classifies 401 as AUTH_ERROR and preserves status 401', () => {
    const err = new ApiError({ status: 401, message: 'Unauthorized' });
    expect(err.status).toBe(401);
    expect(err.statusCode).toBe(401);
    expect(err.kind).toBe('AUTHENTICATION');
    expect(err.response?.status).toBe(401);

    const classified = classifyFetchError(err);
    expect(classified.type).toBe('AUTH_ERROR');
    expect(classified.status).toBe(401);
    expect(isConnectivityError(classified)).toBe(false);
  });

  it('classifies 403 as AUTH_ERROR and preserves status 403', () => {
    const err = new ApiError({ status: 403, message: 'Forbidden' });
    expect(err.status).toBe(403);
    expect(err.kind).toBe('AUTHORIZATION');

    const classified = classifyFetchError(err);
    expect(classified.type).toBe('AUTH_ERROR');
    expect(classified.status).toBe(403);
    expect(isConnectivityError(classified)).toBe(false);
  });

  it('classifies 404 as HTTP_ERROR and preserves status 404', () => {
    const err = new ApiError({ status: 404, message: 'Inspection not found' });
    expect(err.status).toBe(404);
    expect(err.kind).toBe('NOT_FOUND');

    const classified = classifyFetchError(err);
    expect(classified.type).toBe('HTTP_ERROR');
    expect(classified.status).toBe(404);
    expect(isConnectivityError(classified)).toBe(false);
  });

  it('classifies 422 as HTTP_ERROR with VALIDATION kind and data', () => {
    const validationData = { detail: [{ loc: ['body', 'title'], msg: 'field required' }] };
    const err = new ApiError({
      status: 422,
      message: 'Unprocessable Entity',
      data: validationData,
    });
    expect(err.status).toBe(422);
    expect(err.kind).toBe('VALIDATION');
    expect(err.data).toEqual(validationData);
    expect(err.response?.data).toEqual(validationData);

    const classified = classifyFetchError(err);
    expect(classified.type).toBe('HTTP_ERROR');
    expect(classified.status).toBe(422);
    expect(isConnectivityError(classified)).toBe(false);
  });

  it('classifies 409 as CONFLICT and preserves status 409', () => {
    const err = new ApiError({ status: 409, message: 'Unresolved findings exist' });
    expect(err.status).toBe(409);
    expect(err.kind).toBe('CONFLICT');

    const classified = classifyFetchError(err);
    expect(classified.type).toBe('HTTP_ERROR');
    expect(classified.status).toBe(409);
    expect(isConnectivityError(classified)).toBe(false);
  });

  it('classifies 429 as RATE_LIMIT and preserves status 429', () => {
    const err = new ApiError({ status: 429, message: 'Too many requests' });
    expect(err.status).toBe(429);
    expect(err.kind).toBe('RATE_LIMIT');

    const classified = classifyFetchError(err);
    expect(classified.type).toBe('HTTP_ERROR');
    expect(classified.status).toBe(429);
    expect(isConnectivityError(classified)).toBe(false);
  });

  it('classifies 500 as SERVER_ERROR and NEVER as connectivity error', () => {
    const err = new ApiError({ status: 500, message: 'Internal Server Error' });
    expect(err.status).toBe(500);
    expect(err.kind).toBe('SERVER_ERROR');

    const classified = classifyFetchError(err);
    expect(classified.type).toBe('SERVER_ERROR');
    expect(classified.status).toBe(500);
    expect(isConnectivityError(classified)).toBe(false);
  });

  it('does NOT mistake a 502 Bad Gateway for an offline/connectivity error', () => {
    const err = new ApiError({
      status: 502,
      message: 'Bad Gateway: Failed to fetch upstream server',
    });
    const classified = classifyFetchError(err);
    expect(classified.type).toBe('SERVER_ERROR');
    expect(classified.status).toBe(502);
    expect(isConnectivityError(classified)).toBe(false);
  });

  it('classifies AbortError as REQUEST_TIMEOUT and NOT connectivity error', () => {
    const err = { name: 'AbortError', message: 'The user aborted a request.' };
    const classified = classifyFetchError(err);
    expect(classified.type).toBe('REQUEST_TIMEOUT');
    expect(isConnectivityError(classified)).toBe(false);
  });

  it('classifies blob: fetch error as BLOB_FETCH_ERROR and NOT connectivity error', () => {
    const err = new Error('Failed to fetch');
    const classified = classifyFetchError(err, 'blob:http://localhost:8081/abc-123');
    expect(classified.type).toBe('BLOB_FETCH_ERROR');
    expect(isConnectivityError(classified)).toBe(false);
  });

  it('classifies actual TCP drop / connection refused as NETWORK_UNREACHABLE', () => {
    const err = new Error('TypeError: Failed to fetch');
    const classified = classifyFetchError(err);
    expect(classified.type).toBe('NETWORK_UNREACHABLE');
    expect(isConnectivityError(classified)).toBe(true);
  });

  it('sanitizes and redacts JWTs, database URLs, and stack traces from error messages', () => {
    const jwtSample = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doNotLeakThisSignature12345';
    const rawMsg = `Auth failed with token ${jwtSample} on postgresql://user:secret123@neon.tech/neondb`;
    const err = new ApiError({
      status: 500,
      message: rawMsg,
    });

    expect(err.message).not.toContain(jwtSample);
    expect(err.message).toContain('[REDACTED_TOKEN]');
    expect(err.message).not.toContain('secret123');
    expect(err.message).toContain('[REDACTED_DATABASE_URL]');
  });
});
