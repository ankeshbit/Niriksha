import { api } from './api';
import { draftStorage, LocalDraft } from './draftStorage';
import { networkService } from './networkService';
import { Platform } from 'react-native';

export const syncService = {
  async syncDraft(draft: LocalDraft): Promise<any> {
    const isOnline = await networkService.checkReachability();
    if (!isOnline) {
      await draftStorage.updateDraftStatus(draft.clientDraftId, 'PENDING_SYNC', {
        syncError: 'Cannot sync: server is unreachable.',
      });
      throw new Error('Connection unavailable. Local draft remains saved offline.');
    }

    await draftStorage.updateDraftStatus(draft.clientDraftId, 'SYNCING');

    try {
      // 1. Idempotently create or reconcile the inspection record
      const inspection = await api.createInspection({
        product_name: draft.productName,
        brand_name: draft.brandName || undefined,
        category: draft.category,
        location: draft.location,
        batch_number: draft.batchNumber || undefined,
        notes: draft.notes || undefined,
        client_draft_id: draft.clientDraftId,
      });

      // 2. Upload any offline-captured images
      if (draft.images && draft.images.length > 0) {
        for (const img of draft.images) {
          try {
            const formData = new FormData();
            const filename = img.uri.split('/').pop() || `${img.viewType}_panel.jpg`;
            const match = /\.(\w+)$/.exec(filename);
            const type = match ? `image/${match[1]}` : 'image/jpeg';

            if (Platform.OS === 'web') {
              const response = await fetch(img.uri);
              const blob = await response.blob();
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
          } catch (imgErr) {
            console.warn(`[syncService] Image upload warning for ${img.viewType}:`, imgErr);
          }
        }
      }

      // 3. Mark draft as SYNCED
      await draftStorage.updateDraftStatus(draft.clientDraftId, 'SYNCED', {
        syncedInspectionId: inspection.id,
        syncedInspectionNumber: inspection.inspection_number,
        syncError: undefined,
      });

      return inspection;
    } catch (err: any) {
      await draftStorage.updateDraftStatus(draft.clientDraftId, 'PENDING_SYNC', {
        syncError: err.message || 'Sync failed due to network error.',
      });
      throw err;
    }
  },

  async syncAllPendingDrafts(): Promise<{ synced: number; failed: number }> {
    const isOnline = await networkService.checkReachability();
    if (!isOnline) {
      return { synced: 0, failed: 0 };
    }

    const drafts = await draftStorage.getDrafts();
    const pendingDrafts = drafts.filter(
      (d) => d.status === 'PENDING_SYNC' || d.status === 'LOCAL_DRAFT'
    );

    let synced = 0;
    let failed = 0;

    for (const draft of pendingDrafts) {
      try {
        await this.syncDraft(draft);
        synced++;
      } catch (e) {
        failed++;
      }
    }

    return { synced, failed };
  },
};

// Register automatic background sync when network transitions OFFLINE -> ONLINE
networkService.onReconnect(async () => {
  try {
    await syncService.syncAllPendingDrafts();
  } catch (err) {
    console.warn('[syncService] Auto-sync on reconnect warning:', err);
  }
});

