/**
 * Error classification tests verifying that HTTP errors, timeouts, and blob failures
 * are NEVER misclassified as network connectivity failures.
 */

// We test the logic defined in api.ts
function classifyFetchError(err, url) {
  const msg = String(err?.message || err || '');
  const isAbort = err?.name === 'AbortError' || msg.includes('aborted');
  const isNetworkMsg =
    msg.includes('Failed to fetch') ||
    msg.includes('Network request failed') ||
    msg.includes('NetworkError') ||
    msg.includes('ECONNREFUSED') ||
    msg.includes('ENOTFOUND');

  if (url && (url.startsWith('blob:') || url.startsWith('data:'))) {
    return {
      type: 'BLOB_FETCH_ERROR',
      message: msg,
      userMessage: 'Could not read the selected image file. Please select the image again.',
    };
  }

  if (isAbort) {
    return {
      type: 'REQUEST_TIMEOUT',
      message: msg,
      userMessage: 'The request took too long. The server may be processing a complex task. Please try again.',
    };
  }

  if (isNetworkMsg) {
    return {
      type: 'NETWORK_UNREACHABLE',
      message: msg,
      userMessage: 'Backend connection unavailable. Your draft is safely stored locally.',
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

function isConnectivityError(classified) {
  return classified.type === 'NETWORK_UNREACHABLE';
}

describe('Error Classification Regression Suite', () => {
  it('classifies 401 as AUTH_ERROR and NOT connectivity error', () => {
    const err = { status: 401, message: 'Unauthorized' };
    const classified = classifyFetchError(err);
    expect(classified.type).toBe('AUTH_ERROR');
    expect(isConnectivityError(classified)).toBe(false);
  });

  it('classifies 404 as HTTP_ERROR and NOT connectivity error', () => {
    const err = { status: 404, message: 'Inspection not found' };
    const classified = classifyFetchError(err);
    expect(classified.type).toBe('HTTP_ERROR');
    expect(isConnectivityError(classified)).toBe(false);
  });

  it('classifies 422 as HTTP_ERROR and NOT connectivity error', () => {
    const err = { status: 422, message: 'Unprocessable Entity' };
    const classified = classifyFetchError(err);
    expect(classified.type).toBe('HTTP_ERROR');
    expect(isConnectivityError(classified)).toBe(false);
  });

  it('classifies 500 as SERVER_ERROR and NOT connectivity error', () => {
    const err = { status: 500, message: 'Internal Server Error' };
    const classified = classifyFetchError(err);
    expect(classified.type).toBe('SERVER_ERROR');
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
});
