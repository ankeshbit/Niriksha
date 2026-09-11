/**
 * syncService.ts
 *
 * Synchronizes offline local drafts with the NiriKsha backend.
 *
 * Key invariants:
 *  1. One local draft → exactly one backend inspection (client_draft_id idempotency).
 *  2. Image uploads must ALL succeed before AI/OCR analysis is triggered.
 *  3. If ANY upload fails, the draft rolls back to READY_FOR_SYNC; all local
 *     images are preserved; no AI/OCR is started; no duplicate inspection is created.
 *  4. Automatic sync fires when the networkService transitions OFFLINE → ONLINE.
 *     Officers do NOT need to press Retry for normal recovery.
 */

import { api } from './api';
import { draftStorage, LocalDraft, isPendingSync } from './draftStorage';
import { networkService } from './networkService';
import { Platform } from 'react-native';

// ─── Navigation callback type ─────────────────────────────────────────────────

/**
 * Optional callback provided by the UI layer so syncService can navigate to
 * the AnalyzingScreen after a successful sync + image upload.
 * This decouples syncService from React Navigation imports.
 */
export type SyncNavigationCallback = (params: {
  inspectionId: string;
  inspectionNumber: string;
}) => void;

// ─── Progress reporter ────────────────────────────────────────────────────────

export type SyncProgressUpdate =
  | { phase: 'connecting' }
  | { phase: 'creating_inspection' }
  | { phase: 'uploading'; uploaded: number; total: number }
  | { phase: 'starting_analysis' }
  | { phase: 'done'; inspectionId: string; inspectionNumber: string }
  | { phase: 'error'; message: string };

export type SyncProgressListener = (update: SyncProgressUpdate) => void;

// ─── Core sync logic ──────────────────────────────────────────────────────────

export const syncService = {
  async syncDraft(
    draft: LocalDraft,
    onProgress?: SyncProgressListener,
    onNavigate?: SyncNavigationCallback
  ): Promise<any> {
    const emit = (u: SyncProgressUpdate) => {
      try { onProgress?.(u); } catch { /* never let progress callback crash sync */ }
    };

    // ── Pre-flight: verify connectivity ──────────────────────────────────────
    emit({ phase: 'connecting' });
    const isOnline = await networkService.checkReachability();
    if (!isOnline) {
      await draftStorage.updateDraftStatus(draft.clientDraftId, 'READY_FOR_SYNC', {
        syncError: 'Cannot sync: server is unreachable.',
      });
      throw new Error('Connection unavailable. Local draft remains saved offline.');
    }

    await draftStorage.updateDraftStatus(draft.clientDraftId, 'SYNCING');

    try {
      // ── Step 1: Idempotently create or reconcile the backend inspection ───
      emit({ phase: 'creating_inspection' });
      const inspection = await api.createInspection({
        product_name: draft.productName,
        brand_name: draft.brandName || undefined,
        category: draft.category,
        location: draft.location,
        batch_number: draft.batchNumber || undefined,
        notes: draft.notes || undefined,
        client_draft_id: draft.clientDraftId,
      });

      // ── Step 2: Upload canonical locally captured images (one per slot) ──
      const rawImages = draft.images || [];
      const slotMap = new Map<'front' | 'back' | 'side', (typeof rawImages)[0]>();
      for (const img of rawImages) {
        slotMap.set(img.viewType, img);
      }
      const images = Array.from(slotMap.values());
      const total = images.length;
      let uploaded = 0;
      const failedUploads: string[] = [];

      for (const img of images) {
        emit({ phase: 'uploading', uploaded, total });
        try {
          const formData = new FormData();
          const isDataUrl = img.uri.startsWith('data:');
          const filename = isDataUrl
            ? `${img.viewType}_panel.jpg`
            : img.uri.split('/').pop()?.split('?')[0] || `${img.viewType}_panel.jpg`;
          const match = /\.(\w+)$/.exec(filename);
          const type = match ? `image/${match[1]}` : 'image/jpeg';

          if (Platform.OS === 'web') {
            let blob: Blob;
            if (isDataUrl) {
              // Direct base64 Data URL decoding — 100% reliable, zero network/blob dependency
              const [header, base64Data] = img.uri.split(',');
              const mimeMatch = header.match(/:(.*?);/);
              const mime = mimeMatch ? mimeMatch[1] : 'image/jpeg';
              const binaryStr = atob(base64Data);
              const len = binaryStr.length;
              const bytes = new Uint8Array(len);
              for (let i = 0; i < len; i++) {
                bytes[i] = binaryStr.charCodeAt(i);
              }
              blob = new Blob([bytes], { type: mime });
            } else {
              const response = await fetch(img.uri);
              if (!response.ok) {
                throw new Error(`Failed to read draft image (HTTP ${response.status})`);
              }
              blob = await response.blob();
            }
            formData.append('file', blob, filename);
          } else {
            formData.append('file', {
              uri: Platform.OS === 'android' ? img.uri : img.uri.replace('file://', ''),
              name: filename,
              type,
            } as any);
          }
          formData.append('view_type', img.viewType);
          await api.uploadImage(inspection.id, formData);
          uploaded++;
          emit({ phase: 'uploading', uploaded, total });
        } catch (imgErr: any) {
          console.error(`[syncService] Upload FAILED for ${img.viewType}:`, imgErr);
          failedUploads.push(img.viewType);
        }
      }

      // ── Step 3: Abort if any upload failed — preserve ALL local data ──────
      if (failedUploads.length > 0) {
        const errMsg = `Image upload failed for: ${failedUploads.join(', ')}. All local images preserved.`;
        await draftStorage.updateDraftStatus(draft.clientDraftId, 'READY_FOR_SYNC', {
          syncError: errMsg,
          // Keep syncedInspectionId so retry reuses the same backend inspection
          syncedInspectionId: inspection.id,
          syncedInspectionNumber: inspection.inspection_number,
        });
        emit({ phase: 'error', message: errMsg });
        throw new Error(errMsg);
      }

      // ── Step 4: Mark draft as SYNCED ──────────────────────────────────────
      await draftStorage.updateDraftStatus(draft.clientDraftId, 'SYNCED', {
        syncedInspectionId: inspection.id,
        syncedInspectionNumber: inspection.inspection_number,
        syncError: undefined,
      });

      // ── Step 5: Mark ANALYSIS_PENDING then hand off to AnalyzingScreen or run OCR ──
      await draftStorage.updateDraftStatus(draft.clientDraftId, 'ANALYSIS_PENDING');
      emit({ phase: 'done', inspectionId: inspection.id, inspectionNumber: inspection.inspection_number });

      if (onNavigate) {
        // UI layer present — delegate OCR execution to AnalyzingScreen with full live feedback
        try {
          onNavigate({
            inspectionId: inspection.id,
            inspectionNumber: inspection.inspection_number,
          });
        } catch (navErr) {
          console.warn('[syncService] Navigation callback error:', navErr);
        }
      } else {
        // Background sync without UI — run OCR directly
        emit({ phase: 'starting_analysis' });
        try {
          await api.runOCR(inspection.id);
          await draftStorage.updateDraftStatus(draft.clientDraftId, 'ANALYZING');
        } catch (ocrErr: any) {
          console.warn('[syncService] Headless OCR trigger warning:', ocrErr);
        }
      }

      return inspection;
    } catch (err: any) {
      // Only roll back to READY_FOR_SYNC if we haven't already handled the state above
      const current = await draftStorage.getDraft(draft.clientDraftId);
      if (current && (current.status === 'SYNCING')) {
        await draftStorage.updateDraftStatus(draft.clientDraftId, 'READY_FOR_SYNC', {
          syncError: err.message || 'Sync failed due to network error.',
        });
      }
      throw err;
    }
  },

  async syncAllPendingDrafts(
    onProgress?: SyncProgressListener,
    onNavigate?: SyncNavigationCallback
  ): Promise<{ synced: number; failed: number }> {
    const isOnline = await networkService.checkReachability();
    if (!isOnline) {
      return { synced: 0, failed: 0 };
    }

    const drafts = await draftStorage.getDrafts();
    const pendingDrafts = drafts.filter((d) => isPendingSync(d.status));

    let synced = 0;
    let failed = 0;

    for (const draft of pendingDrafts) {
      try {
        await this.syncDraft(draft, onProgress, onNavigate);
        synced++;
      } catch (e) {
        failed++;
      }
    }

    return { synced, failed };
  },
};

// ─── Automatic background sync on OFFLINE → ONLINE transition ────────────────
//
// The networkService fires onReconnect callbacks automatically when connectivity
// is restored. This registration means officers do NOT need to press Retry —
// sync starts automatically.
//
// Note: This background sync does NOT pass a navigation callback (no UI context
// here). The DraftOfflineScreen registers its own onReconnect callback with
// navigation support when it is mounted.

networkService.onReconnect(async () => {
  try {
    await syncService.syncAllPendingDrafts();
  } catch (err) {
    console.warn('[syncService] Auto-sync on reconnect warning:', err);
  }
});
