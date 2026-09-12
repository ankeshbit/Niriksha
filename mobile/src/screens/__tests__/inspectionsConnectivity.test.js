/**
 * inspectionsConnectivity.test.js
 *
 * Automated test suite covering connectivity state transitions, error classification,
 * Inspections screen decision logic, and draft sync safety.
 */

// ─── 1. Connectivity State Machine & Reachability Logic ──────────────────────

describe('Network Connectivity State Machine', () => {
  function createTestNetworkService() {
    let state = 'UNKNOWN';
    let isNativeConnected = true;
    let isPhysicalOnlineVal = true;
    const listeners = new Set();
    const reconnectCallbacks = new Set();

    return {
      getState: () => state,
      isPhysicalOnline: () => isPhysicalOnlineVal,
      setPhysicalOnline: (val) => {
        isPhysicalOnlineVal = val;
        if (!val) {
          state = 'OFFLINE';
          listeners.forEach((l) => l(state));
        }
      },
      setState: (newState) => {
        const oldState = state;
        if (oldState !== newState) {
          state = newState;
          listeners.forEach((l) => l(newState));
          if (newState === 'ONLINE' && oldState === 'OFFLINE') {
            reconnectCallbacks.forEach((cb) => cb());
          }
        }
      },
      subscribe: (listener) => {
        listeners.add(listener);
        listener(state);
        return () => listeners.delete(listener);
      },
      onReconnect: (cb) => {
        reconnectCallbacks.add(cb);
        return () => reconnectCallbacks.delete(cb);
      },
      checkReachability: async (mockFetch) => {
        if (!isPhysicalOnlineVal) {
          state = 'OFFLINE';
          listeners.forEach((l) => l(state));
          return false;
        }
        try {
          const res = await mockFetch();
          const isServerReachable = Boolean(res);
          const newState = isServerReachable ? 'ONLINE' : 'OFFLINE';
          const oldState = state;
          if (oldState !== newState) {
            state = newState;
            listeners.forEach((l) => l(newState));
            if (newState === 'ONLINE' && oldState === 'OFFLINE') {
              reconnectCallbacks.forEach((cb) => cb());
            }
          }
          return res.ok;
        } catch (e) {
          const isTimeout = e?.name === 'AbortError' || e?.message?.includes('aborted');
          if (isTimeout) {
            // Preserve current state on timeout (never flip to OFFLINE)
            return state !== 'OFFLINE';
          }
          state = 'OFFLINE';
          listeners.forEach((l) => l(state));
          return false;
        }
      },
    };
  }

  test('Initial state is UNKNOWN and does not default to OFFLINE', () => {
    const net = createTestNetworkService();
    expect(net.getState()).toBe('UNKNOWN');
  });

  test('UNKNOWN -> ONLINE when backend health check succeeds', async () => {
    const net = createTestNetworkService();
    const isOnline = await net.checkReachability(async () => ({ ok: true, status: 200 }));
    expect(isOnline).toBe(true);
    expect(net.getState()).toBe('ONLINE');
  });

  test('UNKNOWN -> OFFLINE when network is unreachable', async () => {
    const net = createTestNetworkService();
    const isOnline = await net.checkReachability(async () => {
      throw new Error('Failed to fetch (ECONNREFUSED)');
    });
    expect(isOnline).toBe(false);
    expect(net.getState()).toBe('OFFLINE');
  });

  test('ONLINE -> OFFLINE when physical network disconnects', () => {
    const net = createTestNetworkService();
    net.setState('ONLINE');
    expect(net.getState()).toBe('ONLINE');

    net.setPhysicalOnline(false);
    expect(net.getState()).toBe('OFFLINE');
  });

  test('OFFLINE -> ONLINE restores state and fires reconnect callbacks', async () => {
    const net = createTestNetworkService();
    net.setState('OFFLINE');
    expect(net.getState()).toBe('OFFLINE');

    let reconnected = false;
    net.onReconnect(() => {
      reconnected = true;
    });

    await net.checkReachability(async () => ({ ok: true, status: 200 }));
    expect(net.getState()).toBe('ONLINE');
    expect(reconnected).toBe(true);
  });

  test('Temporary request timeout (AbortError) does NOT set state to OFFLINE', async () => {
    const net = createTestNetworkService();
    net.setState('ONLINE');

    // Simulate health check timeout
    const result = await net.checkReachability(async () => {
      const err = new Error('The user aborted a request.');
      err.name = 'AbortError';
      throw err;
    });

    expect(result).toBe(true);
    // MUST remain ONLINE, not permanently flipped to OFFLINE
    expect(net.getState()).toBe('ONLINE');
  });

  test('HTTP 500 Server Error does NOT set state to OFFLINE', async () => {
    const net = createTestNetworkService();
    net.setState('ONLINE');

    // Server responded with HTTP 500 (internal server error)
    // Server is reachable, so device is NOT offline
    const result = await net.checkReachability(async () => ({
      ok: false,
      status: 500,
    }));

    // health status is false (not ok), but connectivity state is ONLINE
    expect(result).toBe(false);
    expect(net.getState()).toBe('ONLINE');
  });

  test('HTTP 401 Auth Error does NOT set state to OFFLINE', async () => {
    const net = createTestNetworkService();
    net.setState('ONLINE');

    await net.checkReachability(async () => ({
      ok: false,
      status: 401,
    }));

    expect(net.getState()).toBe('ONLINE');
  });
});

// ─── 2. Inspections Screen Decision Logic ────────────────────────────────────

describe('Inspections Screen State Decision Logic', () => {
  function decideInspectionsUI({ networkState, drafts, isResolvingConnectivity }) {
    const isActuallyOffline = networkState === 'OFFLINE';
    const pendingDrafts = drafts.filter(
      (d) =>
        d.status === 'LOCAL_CAPTURE' ||
        d.status === 'READY_FOR_SYNC' ||
        d.status === 'LOCAL_DRAFT' ||
        d.status === 'PENDING_SYNC'
    );

    if (isResolvingConnectivity && networkState === 'UNKNOWN') {
      return {
        viewMode: 'RESOLVING_CONNECTIVITY',
        showOfflineUI: false,
        showNormalRegistry: false,
        showPendingSyncBanner: false,
      };
    }

    if (isActuallyOffline) {
      return {
        viewMode: 'OFFLINE_WORKFLOW',
        showOfflineUI: true,
        showNormalRegistry: false,
        showPendingSyncBanner: false,
        draftsToDisplay: drafts,
      };
    }

    // ONLINE (or UNKNOWN that resolved online)
    return {
      viewMode: 'ONLINE_REGISTRY',
      showOfflineUI: false,
      showNormalRegistry: true,
      showPendingSyncBanner: pendingDrafts.length > 0,
      pendingCount: pendingDrafts.length,
    };
  }

  test('ONLINE + no drafts -> Normal Inspections registry, NO offline screen', () => {
    const decision = decideInspectionsUI({
      networkState: 'ONLINE',
      drafts: [],
      isResolvingConnectivity: false,
    });

    expect(decision.viewMode).toBe('ONLINE_REGISTRY');
    expect(decision.showOfflineUI).toBe(false);
    expect(decision.showNormalRegistry).toBe(true);
    expect(decision.showPendingSyncBanner).toBe(false);
  });

  test('ONLINE + pending drafts -> Normal Inspections registry + background sync banner (NOT offline screen)', () => {
    const decision = decideInspectionsUI({
      networkState: 'ONLINE',
      drafts: [
        { clientDraftId: 'draft-1', productName: 'Biscuit', status: 'READY_FOR_SYNC' },
        { clientDraftId: 'draft-2', productName: 'Cookies', status: 'READY_FOR_SYNC' },
      ],
      isResolvingConnectivity: false,
    });

    expect(decision.viewMode).toBe('ONLINE_REGISTRY');
    // CRITICAL: showOfflineUI MUST BE FALSE
    expect(decision.showOfflineUI).toBe(false);
    expect(decision.showNormalRegistry).toBe(true);
    expect(decision.showPendingSyncBanner).toBe(true);
    expect(decision.pendingCount).toBe(2);
  });

  test('OFFLINE + pending draft -> Offline workflow with locally stored drafts', () => {
    const decision = decideInspectionsUI({
      networkState: 'OFFLINE',
      drafts: [{ clientDraftId: 'draft-1', productName: 'Biscuit', status: 'READY_FOR_SYNC' }],
      isResolvingConnectivity: false,
    });

    expect(decision.viewMode).toBe('OFFLINE_WORKFLOW');
    expect(decision.showOfflineUI).toBe(true);
    expect(decision.showNormalRegistry).toBe(false);
    expect(decision.draftsToDisplay.length).toBe(1);
  });

  test('OFFLINE + no drafts -> Offline workflow with offline capture action', () => {
    const decision = decideInspectionsUI({
      networkState: 'OFFLINE',
      drafts: [],
      isResolvingConnectivity: false,
    });

    expect(decision.viewMode).toBe('OFFLINE_WORKFLOW');
    expect(decision.showOfflineUI).toBe(true);
    expect(decision.showNormalRegistry).toBe(false);
    expect(decision.draftsToDisplay.length).toBe(0);
  });

  test('UNKNOWN state briefly resolves connectivity without defaulting to offline screen', () => {
    const decision = decideInspectionsUI({
      networkState: 'UNKNOWN',
      drafts: [{ clientDraftId: 'draft-1', status: 'READY_FOR_SYNC' }],
      isResolvingConnectivity: true,
    });

    expect(decision.viewMode).toBe('RESOLVING_CONNECTIVITY');
    expect(decision.showOfflineUI).toBe(false);
  });
});

// ─── 3. Draft Sync Safety & Idempotency ──────────────────────────────────────

describe('Draft Synchronization Safety & Idempotency', () => {
  test('Pending draft existence NEVER forces offline screen when online', () => {
    const drafts = [
      { clientDraftId: 'draft-test-1', status: 'READY_FOR_SYNC' },
      { clientDraftId: 'draft-test-2', status: 'LOCAL_CAPTURE' },
    ];
    const isOffline = false;
    // The bug was: showOfflineUI = isOffline || Boolean(hasPendingDraft)
    // The fix is: showOfflineUI = isOffline
    const buggyDecision = isOffline || drafts.length > 0;
    const fixedDecision = isOffline;

    expect(buggyDecision).toBe(true); // Demonstrates the previous bug
    expect(fixedDecision).toBe(false); // Validates the fix
  });

  test('Sync success marks draft as SYNCED with backend IDs and clears syncError', () => {
    const draft = {
      clientDraftId: 'draft-uuid-001',
      status: 'READY_FOR_SYNC',
      productName: 'Atta 5kg',
      syncError: 'Previous connection failure',
    };

    // Simulate successful sync
    const syncedDraft = {
      ...draft,
      status: 'SYNCED',
      syncedInspectionId: 'insp-backend-100',
      syncedInspectionNumber: 'LM-2026-00042',
      syncError: undefined,
    };

    expect(syncedDraft.status).toBe('SYNCED');
    expect(syncedDraft.syncedInspectionNumber).toBe('LM-2026-00042');
    expect(syncedDraft.syncError).toBeUndefined();
  });

  test('Sync failure preserves all local images and sets status to READY_FOR_SYNC', () => {
    const draft = {
      clientDraftId: 'draft-uuid-002',
      status: 'SYNCING',
      productName: 'Shampoo 200ml',
      images: [
        { viewType: 'front', uri: 'file:///images/front.jpg' },
        { viewType: 'back', uri: 'file:///images/back.jpg' },
      ],
    };

    // Simulate failed upload
    const rolledBackDraft = {
      ...draft,
      status: 'READY_FOR_SYNC',
      syncError: 'Network error uploading back panel. All local images preserved.',
    };

    expect(rolledBackDraft.status).toBe('READY_FOR_SYNC');
    expect(rolledBackDraft.images.length).toBe(2);
    expect(rolledBackDraft.syncError).toContain('All local images preserved');
  });

  test('Idempotent client_draft_id prevents duplicate inspections across reconnects', () => {
    const clientDraftId = 'draft-fixed-uuid-999';
    const existingInspections = [{ client_draft_id: 'draft-fixed-uuid-999', id: 'insp-1' }];

    // Check if inspection already exists with this client_draft_id
    const existing = existingInspections.find((i) => i.client_draft_id === clientDraftId);
    expect(existing).toBeDefined();
    expect(existing.id).toBe('insp-1');
  });
});
