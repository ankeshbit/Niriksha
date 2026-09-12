import { Platform } from 'react-native';
import { getApiBaseUrl } from './api';

export type ConnectivityState = 'UNKNOWN' | 'ONLINE' | 'OFFLINE';

type Listener = (state: ConnectivityState) => void;
type ReconnectCallback = () => void | Promise<void>;

class NetworkService {
  private state: ConnectivityState = 'UNKNOWN';
  private listeners: Set<Listener> = new Set();
  private reconnectCallbacks: Set<ReconnectCallback> = new Set();
  private isInitialized = false;
  private heartbeatInterval: any = null;
  private isChecking = false;
  private netInfoUnsubscribe: (() => void) | null = null;

  private isNativeConnected = true;

  constructor() {
    this.init();
  }

  public isPhysicalOnline(): boolean {
    if (Platform.OS === 'web' && typeof navigator !== 'undefined' && typeof navigator.onLine === 'boolean') {
      return navigator.onLine;
    }
    return this.isNativeConnected;
  }

  private init() {
    if (this.isInitialized) return;
    this.isInitialized = true;

    // 1. Web runtime physical network event listeners
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      // Physical disconnect -> immediately OFFLINE
      window.addEventListener('offline', () => {
        this.setState('OFFLINE');
      });

      // Physical reconnect -> evaluate backend reachability and transition
      window.addEventListener('online', () => {
        this.checkReachability().catch(() => {});
      });

      // Tab visibility / window focus -> evaluate reachability
      if (typeof document !== 'undefined') {
        document.addEventListener('visibilitychange', () => {
          if (document.visibilityState === 'visible') {
            this.checkReachability().catch(() => {});
          }
        });
      }
      window.addEventListener('focus', () => {
        this.checkReachability().catch(() => {});
      });
    }

    // 2. Native NetInfo listener (Android & iOS)
    try {
      const NetInfo = require('@react-native-community/netinfo');
      if (NetInfo && NetInfo.addEventListener) {
        this.netInfoUnsubscribe = NetInfo.addEventListener((netState: any) => {
          const isConnected = netState.isConnected ?? true;
          this.isNativeConnected = isConnected;

          if (!isConnected) {
            this.setState('OFFLINE');
          } else {
            // Evaluates real FastAPI LAN reachability via /api/health
            this.checkReachability().catch(() => {});
          }
        });
      }
      if (NetInfo && NetInfo.fetch) {
        NetInfo.fetch().then((netState: any) => {
          const isConnected = netState.isConnected ?? true;
          this.isNativeConnected = isConnected;
          if (!isConnected) {
            this.setState('OFFLINE');
          } else {
            this.checkReachability().catch(() => {});
          }
        }).catch(() => {});
      }
    } catch (e) {
      // NetInfo not available in this environment
    }

    // 3. Set initial state based on physical status
    if (!this.isPhysicalOnline()) {
      this.state = 'OFFLINE';
    } else {
      this.checkReachability().catch(() => {});
    }

    // AUDIT-NET-01: Removed unconditional 5-second /api/health polling.
    // Connectivity is now event-driven via:
    //   - Native NetInfo listeners (Android/iOS, lines 61-89)
    //   - Browser online/offline events (web, lines 36-57)
    //   - Tab visibility / window focus events (web, lines 48-57)
    //   - On-demand checkReachability() from syncService / API failures
  }

  public startHeartbeat(intervalMs: number = 5000) {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
    }
    this.heartbeatInterval = setInterval(() => {
      this.checkReachability().catch(() => {});
    }, intervalMs);
  }

  public stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  public reportReachability(isReachable: boolean) {
    if (!isReachable || !this.isPhysicalOnline()) {
      this.setState('OFFLINE');
    } else {
      this.setState('ONLINE');
    }
  }

  public setState(newState: ConnectivityState) {
    const oldState = this.state;
    if (oldState !== newState) {
      this.state = newState;
      this.listeners.forEach((listener) => {
        try {
          listener(newState);
        } catch (e) {
          console.error('[NetworkService] listener error:', e);
        }
      });

      // Trigger automatic sync / reconnect hooks when transitioning to ONLINE from OFFLINE
      if (newState === 'ONLINE' && oldState === 'OFFLINE') {
        this.reconnectCallbacks.forEach((cb) => {
          try {
            cb();
          } catch (e) {
            console.error('[NetworkService] reconnect callback error:', e);
          }
        });
      }
    }
  }

  public getState(): ConnectivityState {
    return this.state;
  }

  public isOnline(): boolean {
    if (!this.isPhysicalOnline()) return false;
    if (this.state === 'ONLINE') return true;
    if (this.state === 'UNKNOWN') {
      // UNKNOWN means we haven't confirmed yet — assume online if physical network says so
      return this.isPhysicalOnline();
    }
    return false;
  }

  public subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => {
      this.listeners.delete(listener);
    };
  }

  public onReconnect(callback: ReconnectCallback): () => void {
    this.reconnectCallbacks.add(callback);
    return () => {
      this.reconnectCallbacks.delete(callback);
    };
  }

  /**
   * Checks whether the NiriKsha backend is reachable by requesting /api/health.
   *
   * FIX-RC-1: Timeout raised from 2500ms → 8000ms.
   *   A 2.5-second cutoff was too aggressive — cold-start or momentary load on the
   *   backend could trip it, falsely marking the app OFFLINE during a real session.
   *
   * FIX-RC-2: When a concurrent check is already in progress (isChecking=true),
   *   we now return 'true' if the physical connection is online (optimistic) instead
   *   of returning false when state === 'UNKNOWN'. The previous code returned
   *   `this.state === 'ONLINE'` which evaluates to false for UNKNOWN, blocking sync.
   *
   * FIX-RC-TIMEOUT: An AbortError (request timeout) is now treated differently from
   *   a genuine network failure. A timeout means the backend might just be slow (e.g.
   *   PaddleOCR warming up), NOT that it is unreachable. We do not flip to OFFLINE on
   *   a timeout alone — we preserve the current state and log a warning.
   */
  public async checkReachability(timeoutMs: number = 8000): Promise<boolean> {
    // Check physical connectivity FIRST
    if (!this.isPhysicalOnline()) {
      this.setState('OFFLINE');
      return false;
    }

    // FIX-RC-2: If a check is already running, don't block the caller.
    // Return optimistically-true when physical is online, rather than false for UNKNOWN.
    if (this.isChecking) {
      return this.isPhysicalOnline();
    }
    this.isChecking = true;

    const baseUrl = getApiBaseUrl();
    const url = `${baseUrl}/api/health`;

    try {
      const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
      const timeoutId = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;

      const response = await fetch(url, {
        method: 'GET',
        headers: { 'Cache-Control': 'no-cache' },
        signal: controller ? controller.signal : undefined,
      });

      if (timeoutId) clearTimeout(timeoutId);

      // Re-verify physical status in case it disconnected during fetch
      if (!this.isPhysicalOnline()) {
        this.setState('OFFLINE');
        return false;
      }

      // HTTP response received means device successfully reached the server.
      // Server errors (500/502/503) are application errors, NOT network disconnects.
      const isServerReachable = Boolean(response);
      this.setState(isServerReachable ? 'ONLINE' : 'OFFLINE');
      return response.ok;
    } catch (e: any) {
      // FIX-RC-TIMEOUT: Distinguish timeout (AbortError) from network unreachable.
      // A timeout means the backend is slow, not necessarily gone.
      // Do NOT flip to OFFLINE on a health-check timeout alone — preserve current state.
      const isTimeout = e?.name === 'AbortError' || e?.message?.includes('aborted');
      if (isTimeout) {
        console.warn(
          `[NetworkService] Health check timed out after ${timeoutMs}ms. ` +
          'Backend may be processing (OCR/cold-start). Preserving current connectivity state.'
        );
        // On timeout: if we were ONLINE, stay ONLINE. If UNKNOWN, stay UNKNOWN (optimistic).
        // Only genuine connection errors (not timeouts) should flip to OFFLINE.
        return this.state !== 'OFFLINE';
      }

      // Genuine network failure (connection refused, DNS failure, etc.)
      console.warn('[NetworkService] Health check failed (network unreachable):', e?.message);
      this.setState('OFFLINE');
      return false;
    } finally {
      this.isChecking = false;
    }
  }

  /**
   * Returns diagnostic info for development/debugging.
   * Safe to display — contains no credentials or tokens.
   */
  public getDiagnostics(): {
    apiBaseUrl: string;
    platform: string;
    physicalOnline: boolean;
    networkState: ConnectivityState;
  } {
    return {
      apiBaseUrl: getApiBaseUrl(),
      platform: Platform.OS,
      physicalOnline: this.isPhysicalOnline(),
      networkState: this.state,
    };
  }
}

export const networkService = new NetworkService();


