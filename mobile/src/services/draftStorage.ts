import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

export interface DraftImage {
  viewType: 'front' | 'back' | 'side';
  uri: string;
  savedAt: string;
}

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
  status: 'LOCAL_DRAFT' | 'PENDING_SYNC' | 'SYNCING' | 'SYNCED';
  createdAt: string;
  updatedAt: string;
  syncedInspectionId?: string;
  syncedInspectionNumber?: string;
  syncError?: string;
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
    status: LocalDraft['status'],
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

