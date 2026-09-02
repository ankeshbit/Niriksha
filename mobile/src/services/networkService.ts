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

  constructor() {
    this.init();
  }

  public isPhysicalOnline(): boolean {
    if (Platform.OS === 'web' && typeof navigator !== 'undefined' && typeof navigator.onLine === 'boolean') {
      return navigator.onLine;
    }
    return true;
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
          const isInternetReachable = netState.isInternetReachable;

          if (!isConnected || isInternetReachable === false) {
            this.setState('OFFLINE');
          } else {
            this.checkReachability().catch(() => {});
          }
        });
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

    // 4. Background heartbeat (5s) for backend reachability fallback
    this.startHeartbeat(5000);
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

  public async checkReachability(timeoutMs: number = 2500): Promise<boolean> {
    // Check physical connectivity FIRST
    if (!this.isPhysicalOnline()) {
      this.setState('OFFLINE');
      return false;
    }

    if (this.isChecking) {
      return this.state === 'ONLINE';
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

      const isReachable = response.ok;
      this.setState(isReachable ? 'ONLINE' : 'OFFLINE');
      return isReachable;
    } catch (e) {
      this.setState('OFFLINE');
      return false;
    } finally {
      this.isChecking = false;
    }
  }
}

export const networkService = new NetworkService();


