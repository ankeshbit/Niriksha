import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import type { ImageQualityResult } from './imageQualityService';

export interface DraftImage {
  viewType: 'front' | 'back' | 'side';
  uri: string;
  savedAt: string;
  /** On-device quality check result — populated after checkImageQuality() */
  qualityResult?: ImageQualityResult;
}

/**
 * Draft lifecycle states.
 *
 * LOCAL_CAPTURE    — Images being captured offline; draft not yet complete.
 * READY_FOR_SYNC   — Capture phase complete; waiting for connectivity.
 * SYNCING          — Sync in progress (inspection creation + image upload).
 * SYNCED           — Backend inspection created and all images uploaded.
 * ANALYSIS_PENDING — Sync complete; waiting to trigger OCR/AI analysis.
 * ANALYZING        — OCR/AI analysis triggered on server.
 * COMPLETED        — Full workflow complete.
 *
 * Legacy aliases (preserved for backwards compatibility):
 *  LOCAL_DRAFT  → equivalent to LOCAL_CAPTURE
 *  PENDING_SYNC → equivalent to READY_FOR_SYNC
 */
export type DraftStatus =
  | 'LOCAL_DRAFT'       // legacy alias for LOCAL_CAPTURE
  | 'LOCAL_CAPTURE'     // actively capturing images offline
  | 'PENDING_SYNC'      // legacy alias for READY_FOR_SYNC
  | 'READY_FOR_SYNC'    // capture complete, waiting for connectivity
  | 'SYNCING'           // sync in progress
  | 'SYNCED'            // backend inspection + images confirmed
  | 'ANALYSIS_PENDING'  // about to trigger OCR
  | 'ANALYZING'         // OCR running
  | 'COMPLETED';        // full workflow done

export interface LocalDraft {
  clientDraftId: string; // e.g. "draft-9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
  productName: string;
  brandName: string;
  category: 'Packaged Food' | 'Household/Personal Care';
  location: string;
  batchNumber?: string;
  manufacturer?: string;
  source?: string;
  inspectionContext?: 'Retail' | 'Warehouse' | 'E-commerce';
  notes?: string;
  images: DraftImage[];
  status: DraftStatus;
  createdAt: string;
  updatedAt: string;
  syncedInspectionId?: string;
  syncedInspectionNumber?: string;
  syncError?: string;
}

/** Returns true for any status that means the draft needs to be synced. */
export function isPendingSync(status: DraftStatus): boolean {
  return status === 'LOCAL_DRAFT' || status === 'LOCAL_CAPTURE' ||
    status === 'PENDING_SYNC' || status === 'READY_FOR_SYNC';
}

const DRAFTS_STORAGE_KEY = 'legal_metrology_offline_drafts_v1';

let memoryDrafts: LocalDraft[] = [];

function generateUUID(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

type DraftsListener = (drafts: LocalDraft[]) => void;
const draftListeners: Set<DraftsListener> = new Set();

export const draftStorage = {
  generateClientDraftId(): string {
    return `draft-${generateUUID()}`;
  },

  subscribe(listener: DraftsListener): () => void {
    draftListeners.add(listener);
    this.getDrafts().then((d) => listener(d)).catch(() => listener(memoryDrafts));
    return () => {
      draftListeners.delete(listener);
    };
  },

  async getDrafts(): Promise<LocalDraft[]> {
    try {
      if (Platform.OS === 'web') {
        if (typeof localStorage !== 'undefined') {
          const raw = localStorage.getItem(DRAFTS_STORAGE_KEY);
          if (raw) {
            memoryDrafts = JSON.parse(raw);
            return memoryDrafts;
          }
        }
      } else {
        const raw = await SecureStore.getItemAsync(DRAFTS_STORAGE_KEY);
        if (raw) {
          memoryDrafts = JSON.parse(raw);
          return memoryDrafts;
        }
      }
    } catch (e) {
      console.warn('[draftStorage] getDrafts fallback error:', e);
    }
    return memoryDrafts;
  },

  async saveDraft(draft: LocalDraft): Promise<void> {
    const drafts = await this.getDrafts();
    const idx = drafts.findIndex((d) => d.clientDraftId === draft.clientDraftId);
    if (idx >= 0) {
      drafts[idx] = { ...draft, updatedAt: new Date().toISOString() };
    } else {
      drafts.unshift({ ...draft, updatedAt: new Date().toISOString() });
    }
    memoryDrafts = drafts;
    await this.persistDrafts(drafts);
  },

  async getDraft(clientDraftId: string): Promise<LocalDraft | null> {
    const drafts = await this.getDrafts();
    return drafts.find((d) => d.clientDraftId === clientDraftId) || null;
  },

  async getLatestDraft(): Promise<LocalDraft | null> {
    const drafts = await this.getDrafts();
    return drafts.length > 0 ? drafts[0] : null;
  },

  async updateDraftStatus(
    clientDraftId: string,
    status: DraftStatus,
    extra?: Partial<LocalDraft>
  ): Promise<void> {
    const drafts = await this.getDrafts();
    const idx = drafts.findIndex((d) => d.clientDraftId === clientDraftId);
    if (idx >= 0) {
      drafts[idx] = {
        ...drafts[idx],
        status,
        ...extra,
        updatedAt: new Date().toISOString(),
      };
      memoryDrafts = drafts;
      await this.persistDrafts(drafts);
    }
  },

  async addDraftImage(
    clientDraftId: string,
    image: { viewType: 'front' | 'back' | 'side'; uri: string }
  ): Promise<void> {
    const drafts = await this.getDrafts();
    const idx = drafts.findIndex((d) => d.clientDraftId === clientDraftId);
    if (idx >= 0) {
      const existingImages = drafts[idx].images || [];
      const updatedImages = existingImages.filter((img) => img.viewType !== image.viewType);
      updatedImages.push({
        ...image,
        savedAt: new Date().toISOString(),
      });
      drafts[idx] = {
        ...drafts[idx],
        images: updatedImages,
        updatedAt: new Date().toISOString(),
      };
      memoryDrafts = drafts;
      await this.persistDrafts(drafts);
    }
  },

  /**
   * Saves a draft image WITH its on-device quality check result.
   * Replaces any existing image for the same viewType slot.
   * Never deletes a previously stored image until this call succeeds.
   */
  async addDraftImageWithQuality(
    clientDraftId: string,
    image: {
      viewType: 'front' | 'back' | 'side';
      uri: string;
      qualityResult: ImageQualityResult;
    }
  ): Promise<void> {
    const drafts = await this.getDrafts();
    const idx = drafts.findIndex((d) => d.clientDraftId === clientDraftId);
    if (idx >= 0) {
      const existingImages = drafts[idx].images || [];
      const updatedImages = existingImages.filter((img) => img.viewType !== image.viewType);
      updatedImages.push({
        viewType: image.viewType,
        uri: image.uri,
        savedAt: new Date().toISOString(),
        qualityResult: image.qualityResult,
      });
      drafts[idx] = {
        ...drafts[idx],
        images: updatedImages,
        updatedAt: new Date().toISOString(),
      };
      memoryDrafts = drafts;
      await this.persistDrafts(drafts);
    }
  },

  async deleteDraft(clientDraftId: string): Promise<void> {
    const drafts = await this.getDrafts();
    const filtered = drafts.filter((d) => d.clientDraftId !== clientDraftId);
    memoryDrafts = filtered;
    await this.persistDrafts(filtered);
  },

  async clearAllDrafts(): Promise<void> {
    memoryDrafts = [];
    await this.persistDrafts([]);
  },

  async persistDrafts(drafts: LocalDraft[]): Promise<void> {
    const jsonStr = JSON.stringify(drafts);
    try {
      if (Platform.OS === 'web') {
        if (typeof localStorage !== 'undefined') {
          localStorage.setItem(DRAFTS_STORAGE_KEY, jsonStr);
        }
      } else {
        await SecureStore.setItemAsync(DRAFTS_STORAGE_KEY, jsonStr);
      }
    } catch (e) {
      console.warn('[draftStorage] persistDrafts error:', e);
    }

    draftListeners.forEach((listener) => {
      try {
        listener(drafts);
      } catch (err) {
        console.error('[draftStorage] listener error:', err);
      }
    });
  },
};
