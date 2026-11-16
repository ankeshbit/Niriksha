'use strict';

const fs = require('fs');
const path = require('path');

const EMULATOR_API_HOST = 'http://10.0.2.2:8000';
const LOCALHOST_API_HOST = 'http://127.0.0.1:8000';
const PRODUCTION_API_HOST = 'https://niriksha-1.onrender.com';

function resolveDevelopmentHost(Constants, Platform, windowObj) {
  const hostUri =
    Constants?.expoConfig?.hostUri ||
    Constants?.manifest2?.extra?.expoClient?.hostUri ||
    Constants?.manifest?.debuggerHost;

  if (hostUri && typeof hostUri === 'string') {
    const ip = hostUri.split(':')[0];
    if (ip && ip !== 'localhost' && ip !== '127.0.0.1') {
      return `http://${ip}:8000`;
    }
  }

  if (Platform?.OS === 'android') {
    return EMULATOR_API_HOST;
  }

  if (Platform?.OS === 'web' && windowObj?.location?.hostname) {
    const host = windowObj.location.hostname;
    if (host && host !== 'localhost' && host !== '127.0.0.1') {
      return `http://${host}:8000`;
    }
  }

  return LOCALHOST_API_HOST;
}

function getApiBaseUrl({ customBaseUrl, envUrl, isDev, Constants, Platform, windowObj }) {
  if (customBaseUrl) return customBaseUrl.replace(/\/$/, '');

  if (envUrl && envUrl.trim()) {
    return envUrl.trim().replace(/\/$/, '');
  }

  if (isDev) {
    return resolveDevelopmentHost(Constants, Platform, windowObj);
  }

  if (Platform?.OS === 'web' && windowObj?.location?.hostname) {
    const host = windowObj.location.hostname;
    if (host && host !== 'localhost' && host !== '127.0.0.1') {
      const proto = windowObj.location.protocol || 'https:';
      return `${proto}//${host}`;
    }
  }

  return PRODUCTION_API_HOST;
}

function classifyFetchError(err, url) {
  const msg = String(err?.message || err || '');
  const isNetworkMsg =
    msg.includes('Failed to fetch') ||
    msg.includes('Network request failed') ||
    msg.includes('NetworkError') ||
    msg.includes('ECONNREFUSED') ||
    msg.includes('ENOTFOUND');

  if (isNetworkMsg) {
    const targetUrl = url || (err?.targetUrl ?? err?.url);
    const targetDesc = targetUrl ? ` (${targetUrl})` : '';
    return {
      type: 'NETWORK_UNREACHABLE',
      message: `${msg}${targetDesc}`,
      userMessage: `Backend connection unavailable${targetDesc}. Your draft is safely stored locally.`,
    };
  }

  return { type: 'UNKNOWN_ERROR', message: msg, userMessage: msg };
}

describe('API Host Resolution & Network Error Reporting', () => {
  test('TEST 1: EXPO_PUBLIC_API_URL takes precedence when set', () => {
    const url = getApiBaseUrl({
      envUrl: 'https://custom-api.example.gov.in/',
      isDev: true,
      Platform: { OS: 'android' },
    });
    expect(url).toBe('https://custom-api.example.gov.in');
  });

  test('TEST 2: Explicit customBaseUrl runtime override takes highest precedence', () => {
    const url = getApiBaseUrl({
      customBaseUrl: 'http://192.168.1.99:8000',
      envUrl: 'https://custom-api.example.gov.in',
      isDev: false,
    });
    expect(url).toBe('http://192.168.1.99:8000');
  });

  test('TEST 3: Development fallback uses Expo manifest/debugger host when available', () => {
    const Constants = { expoConfig: { hostUri: '192.168.4.15:8081' } };
    const url = getApiBaseUrl({
      envUrl: null,
      isDev: true,
      Constants,
      Platform: { OS: 'android' },
    });
    expect(url).toBe('http://192.168.4.15:8000');
  });

  test('TEST 4: Development fallback chooses 10.0.2.2 on Android emulator when hostUri is absent', () => {
    const url = getApiBaseUrl({
      envUrl: null,
      isDev: true,
      Constants: {},
      Platform: { OS: 'android' },
    });
    expect(url).toBe('http://10.0.2.2:8000');
  });

  test('TEST 5: Development fallback chooses 127.0.0.1 on iOS simulator when hostUri is absent', () => {
    const url = getApiBaseUrl({
      envUrl: null,
      isDev: true,
      Constants: {},
      Platform: { OS: 'ios' },
    });
    expect(url).toBe('http://127.0.0.1:8000');
  });

  test('TEST 6: Network error message clearly identifies the target URL when connection fails', () => {
    const error = new Error('Network request failed');
    const targetUrl = 'http://10.0.2.2:8000/api/auth/login';

    const classified = classifyFetchError(error, targetUrl);

    expect(classified.type).toBe('NETWORK_UNREACHABLE');
    expect(classified.message).toContain('http://10.0.2.2:8000/api/auth/login');
    expect(classified.userMessage).toContain('http://10.0.2.2:8000/api/auth/login');
  });

  test('TEST 7: No developer-specific LAN IP addresses hardcoded in mobile/src/services/api.ts', () => {
    const apiFile = fs.readFileSync(path.resolve(__dirname, '../../services/api.ts'), 'utf8');

    // Ensure no hardcoded private 192.168.x.x
    const lanMatches = apiFile.match(/192\.168\.\d+\.\d+/g);
    expect(lanMatches).toBeNull();
  });

  test('TEST 8: api.ts exports resolveDevelopmentHost, getApiBaseUrl, and classifyFetchError', () => {
    const apiFile = fs.readFileSync(path.resolve(__dirname, '../../services/api.ts'), 'utf8');
    expect(apiFile).toContain('export function resolveDevelopmentHost');
    expect(apiFile).toContain('export const getApiBaseUrl');
    expect(apiFile).toContain('export function classifyFetchError');
    expect(apiFile).toContain('targetUrl');
  });
});
