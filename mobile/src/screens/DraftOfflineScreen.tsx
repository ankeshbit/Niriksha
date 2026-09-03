/**
 * DraftOfflineScreen.tsx
 *
 * Shows the state of a locally saved inspection draft.
 *
 * Key behaviors:
 *  - Offline: "Inspection Saved Locally / Waiting for Connection"
 *  - When connectivity returns: automatically starts sync WITHOUT requiring Retry.
 *  - Shows sync progress: Connecting → Creating inspection → Uploading N images → Starting AI…
 *  - After successful sync: navigates to the AnalyzingScreen automatically.
 *  - Retry Connection button remains as a MANUAL FALLBACK only.
 *  - Never implies offline AI/OCR is running.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { BottomNav } from '../components/BottomNav';
import { ProfileAvatar } from '../components/ProfileAvatar';
import { useNavigation, useRoute, RouteProp, useFocusEffect } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';
import { networkService, ConnectivityState } from '../services/networkService';
import { draftStorage, LocalDraft, isPendingSync } from '../services/draftStorage';
import { syncService, SyncProgressUpdate } from '../services/syncService';

// ─── Sync progress phases for the UI ─────────────────────────────────────────

type UISyncPhase =
  | 'idle'
  | 'connecting'
  | 'creating'
  | 'uploading'
  | 'starting_analysis'
  | 'done'
  | 'error';

interface SyncProgressState {
  phase: UISyncPhase;
  uploadedCount: number;
  totalCount: number;
  errorMessage?: string;
}

// ─── Component ────────────────────────────────────────────────────────────────

export const DraftOfflineScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'DraftOffline'>>();
  const paramDraftId = route.params?.clientDraftId;

  const [networkState, setNetworkState] = useState<ConnectivityState>(networkService.getState());
  const [currentDraft, setCurrentDraft] = useState<LocalDraft | null>(null);
  const [allDrafts, setAllDrafts] = useState<LocalDraft[]>([]);
  const [loading, setLoading] = useState(true);

  // Sync progress state
  const [syncing, setSyncing] = useState(false);
  const [syncProgress, setSyncProgress] = useState<SyncProgressState>({
    phase: 'idle',
    uploadedCount: 0,
    totalCount: 0,
  });

  // Guard to prevent concurrent sync calls
  const syncInFlightRef = useRef(false);

  // ─── Draft loader ──────────────────────────────────────────────────────────

  const updateDraftSelection = (drafts: LocalDraft[]) => {
    setAllDrafts(drafts);
    if (paramDraftId) {
      const found = drafts.find((d) => d.clientDraftId === paramDraftId);
      if (found) {
        setCurrentDraft(found);
        return;
      }
    }
    const pending = drafts.find((d) => isPendingSync(d.status));
    setCurrentDraft(pending || (drafts.length > 0 ? drafts[0] : null));
  };

  const loadDraftData = async () => {
    try {
      const drafts = await draftStorage.getDrafts();
      updateDraftSelection(drafts);
    } catch (e) {
      console.warn('[DraftOfflineScreen] loadDraftData error:', e);
    } finally {
      setLoading(false);
    }
  };

  useFocusEffect(
    useCallback(() => {
      networkService.checkReachability().then((isOnline) => {
        setNetworkState(isOnline ? 'ONLINE' : 'OFFLINE');
      });
      loadDraftData();
    }, [paramDraftId])
  );

  useEffect(() => {
    const unsubNet = networkService.subscribe((state) => {
      setNetworkState(state);
      if (state === 'ONLINE') {
        loadDraftData();
      }
    });

    const unsubDrafts = draftStorage.subscribe((drafts) => {
      updateDraftSelection(drafts);
      setLoading(false);
    });

    return () => {
      unsubNet();
      unsubDrafts();
    };
  }, [paramDraftId]);

  // ─── Core auto-sync logic ──────────────────────────────────────────────────

  /**
   * Runs synchronization for the current draft.
   * Updates the UI with progress stages.
   * Navigates to AnalyzingScreen on success.
   * This is the SAME function used by both auto-sync and the manual Retry button.
   */
  const runSync = useCallback(async (draft: LocalDraft) => {
    if (syncInFlightRef.current) return;
    syncInFlightRef.current = true;
    setSyncing(true);
    setSyncProgress({ phase: 'connecting', uploadedCount: 0, totalCount: draft.images?.length || 0 });

    try {
      await syncService.syncDraft(
        draft,
        // Progress callback
        (update: SyncProgressUpdate) => {
          switch (update.phase) {
            case 'connecting':
              setSyncProgress((p) => ({ ...p, phase: 'connecting' }));
              break;
            case 'creating_inspection':
              setSyncProgress((p) => ({ ...p, phase: 'creating' }));
              break;
            case 'uploading':
              setSyncProgress((p) => ({
                ...p,
                phase: 'uploading',
                uploadedCount: update.uploaded,
                totalCount: update.total,
              }));
              break;
            case 'starting_analysis':
              setSyncProgress((p) => ({ ...p, phase: 'starting_analysis' }));
              break;
            case 'done':
              setSyncProgress((p) => ({ ...p, phase: 'done' }));
              break;
            case 'error':
              setSyncProgress((p) => ({ ...p, phase: 'error', errorMessage: update.message }));
              break;
          }
        },
        // Navigation callback — fires automatically after successful sync + OCR trigger
        ({ inspectionId, inspectionNumber }) => {
          // Small delay so the officer sees the "Starting AI Analysis..." state
          setTimeout(() => {
            navigation.replace('Analyzing', { inspectionId, inspectionNumber });
          }, 1200);
        }
      );
    } catch (syncErr: any) {
      setSyncProgress({
        phase: 'error',
        uploadedCount: 0,
        totalCount: 0,
        errorMessage: syncErr.message || 'Sync could not be completed.',
      });
    } finally {
      syncInFlightRef.current = false;
      setSyncing(false);
      await loadDraftData();
    }
  }, [navigation]);

  /**
   * Auto-sync wired to the OFFLINE → ONLINE transition.
   * Officers do NOT need to press Retry for normal recovery.
   */
  useEffect(() => {
    const unsubReconnect = networkService.onReconnect(() => {
      // Load the latest draft state and auto-sync if there's a pending draft
      draftStorage.getDraft(paramDraftId || '').then((draft) => {
        const target = draft || currentDraft;
        if (target && isPendingSync(target.status) && !syncInFlightRef.current) {
          runSync(target);
        }
      });
    });

    return () => unsubReconnect();
  }, [paramDraftId, currentDraft, runSync]);

  // ─── Manual retry handler ──────────────────────────────────────────────────

  const handleRetryConnection = async () => {
    const isOnline = await networkService.checkReachability();
    if (!isOnline) {
      Alert.alert(
        'Connection Unavailable',
        'Could not reach NiriKsha Central Server. Your draft remains safely stored on this device.'
      );
      return;
    }

    if (currentDraft && isPendingSync(currentDraft.status)) {
      await runSync(currentDraft);
    } else if (currentDraft?.status === 'SYNCED') {
      Alert.alert(
        'Already Synchronized',
        'This inspection is already synchronized with the Central Server.',
        [{ text: 'OK', onPress: () => navigation.navigate('Dashboard') }]
      );
    } else {
      Alert.alert(
        'Connection Restored',
        'NiriKsha Central Server is online and ready for inspections.',
        [{ text: 'OK', onPress: () => navigation.navigate('Dashboard') }]
      );
    }
  };

  // ─── Derived state ─────────────────────────────────────────────────────────

  const isOffline = networkState === 'OFFLINE';
  const hasPendingDraft = currentDraft && isPendingSync(currentDraft.status);
  const showOfflineUI = isOffline || Boolean(hasPendingDraft) || syncing;

  const dateStr = currentDraft?.createdAt
    ? new Date(currentDraft.createdAt).toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
    : new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

  const displayDraftId = currentDraft?.clientDraftId
    ? currentDraft.clientDraftId.length > 20
      ? `${currentDraft.clientDraftId.substring(0, 16)}...`
      : currentDraft.clientDraftId
    : 'draft-offline';

  // ─── Sync progress UI ──────────────────────────────────────────────────────

  const renderSyncProgress = () => {
    const { phase, uploadedCount, totalCount, errorMessage } = syncProgress;

    const phaseLabel = () => {
      switch (phase) {
        case 'connecting': return 'Connection Restored';
        case 'creating': return 'Syncing Inspection...';
        case 'uploading':
          return totalCount > 0
            ? `Uploading ${uploadedCount} of ${totalCount} images...`
            : 'Uploading images...';
        case 'starting_analysis': return 'Starting AI Analysis...';
        case 'done': return 'Inspection synchronized';
        case 'error': return 'Sync issue — draft preserved';
        default: return 'Preparing sync...';
      }
    };

    const isError = phase === 'error';

    return (
      <View style={[styles.syncProgressCard, isError && styles.syncProgressCardError]}>
        <View style={styles.syncProgressHeader}>
          {isError ? (
            <MaterialIcons name="error-outline" size={20} color={colors.statusAmberText} />
          ) : phase === 'done' ? (
            <MaterialIcons name="check-circle" size={20} color={colors.statusGreenText} />
          ) : (
            <ActivityIndicator size="small" color={colors.primary} />
          )}
          <Text style={[styles.syncProgressTitle, isError && styles.syncProgressTitleError]}>
            {phaseLabel()}
          </Text>
        </View>

        {/* Step indicators */}
        <View style={styles.syncSteps}>
          {[
            { key: 'connecting', label: 'Connection Restored' },
            { key: 'creating', label: 'Syncing Inspection' },
            { key: 'uploading', label: `Uploading Images (${uploadedCount}/${totalCount})` },
            { key: 'starting_analysis', label: 'Starting AI Analysis' },
          ].map(({ key, label }, idx) => {
            const phases: UISyncPhase[] = ['connecting', 'creating', 'uploading', 'starting_analysis', 'done'];
            const currentIdx = phases.indexOf(phase as UISyncPhase);
            const stepIdx = phases.indexOf(key as UISyncPhase);
            const isDone = currentIdx > stepIdx || phase === 'done';
            const isActive = currentIdx === stepIdx && !isError;

            return (
              <View key={key} style={styles.syncStepRow}>
                <MaterialIcons
                  name={isDone ? 'check-circle' : isActive ? 'radio-button-checked' : 'radio-button-unchecked'}
                  size={15}
                  color={isDone ? colors.statusGreenText : isActive ? colors.primary : colors.outline}
                />
                <Text style={[
                  styles.syncStepText,
                  isDone && styles.syncStepTextDone,
                  isActive && styles.syncStepTextActive,
                ]}>
                  {label}
                </Text>
              </View>
            );
          })}
        </View>

        {isError && errorMessage && (
          <Text style={styles.syncErrorNote}>
            {errorMessage} All your captured data is safely stored.
          </Text>
        )}
      </View>
    );
  };

  // ─── Render ────────────────────────────────────────────────────────────────

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
      <View style={styles.container}>
        {/* Top Header */}
        <View style={styles.topHeader}>
          <TouchableOpacity
            style={styles.backButton}
            onPress={() => navigation.navigate('Dashboard')}
            activeOpacity={0.7}
          >
            <MaterialIcons name="arrow-back" size={24} color={colors.primary} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>NiriKsha</Text>
          <ProfileAvatar size={36} />
        </View>

        {/* Connection status banner */}
        {isOffline && !syncing && (
          <View style={styles.warningBanner}>
            <MaterialIcons name="wifi-off" size={18} color={colors.statusAmberText} />
            <Text style={styles.warningBannerText}>No Connection — Inspection Saved Locally</Text>
          </View>
        )}
        {!isOffline && syncing && (
          <View style={styles.onlineSyncBanner}>
            <MaterialIcons name="sync" size={18} color={colors.statusGreenText} />
            <Text style={styles.onlineSyncBannerText}>Connection Restored — Syncing Automatically</Text>
          </View>
        )}

        <ScrollView style={{ flex: 1 }} contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          {loading ? (
            <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
          ) : showOfflineUI ? (
            <>
              {/* Instruction text */}
              <Text style={styles.instructionText}>
                {syncing
                  ? 'Connection restored. Synchronizing your inspection automatically...'
                  : hasPendingDraft
                  ? 'Inspection Saved Locally — Waiting for Connection'
                  : 'Operating in offline mode. Local drafts will sync when connectivity returns.'}
              </Text>

              {/* Sync progress card — shown while syncing or after sync completes/fails */}
              {(syncing || syncProgress.phase !== 'idle') && renderSyncProgress()}

              {/* Draft info card */}
              {!syncing && (
                <View style={styles.centralCard}>
                  <View style={styles.centralCardHeader}>
                    <MaterialIcons name="content-paste" size={20} color={colors.onSurfaceVariant} />
                    <Text style={styles.centralCardHeaderText}>DRAFT SAVED LOCALLY</Text>
                  </View>

                  <View style={styles.centralCardBody}>
                    <View style={styles.infoRow}>
                      <Text style={styles.infoLabel}>ID</Text>
                      <Text style={styles.infoValueBold}>{displayDraftId}</Text>
                    </View>

                    <View style={styles.infoRow}>
                      <Text style={styles.infoLabel}>Product</Text>
                      <Text style={styles.infoValueBold}>
                        {currentDraft?.productName || 'Unknown product'}
                      </Text>
                    </View>

                    <View style={styles.cardFooterRow}>
                      <View style={styles.imagesSavedBox}>
                        <MaterialIcons name="image" size={14} color={colors.onSurfaceVariant} />
                        <Text style={styles.imagesSavedText}>
                          {currentDraft?.images?.length || 0} images saved · {dateStr}
                        </Text>
                      </View>

                      <View style={styles.pendingBadge}>
                        <MaterialIcons
                          name="radio-button-checked"
                          size={14}
                          color={colors.statusAmberText}
                        />
                        <Text style={styles.pendingBadgeText}>
                          {currentDraft?.status === 'SYNCED' ? 'SYNCED' : 'PENDING SYNC'}
                        </Text>
                      </View>
                    </View>
                  </View>
                </View>
              )}

              {/* Checklist card */}
              {!syncing && (
                <View style={styles.checklistCard}>
                  <Text style={styles.checklistTitle}>Stored on this device:</Text>

                  <View style={styles.checklistItemsList}>
                    <View style={styles.checkItemRow}>
                      <MaterialIcons name="check-circle" size={18} color={colors.statusGreenText} />
                      <Text style={styles.checkItemText}>Inspection details</Text>
                    </View>

                    <View style={styles.checkItemRow}>
                      <MaterialIcons name="check-circle" size={18} color={colors.statusGreenText} />
                      <Text style={styles.checkItemText}>
                        {currentDraft?.images?.length || 0} package images (locally stored, quality-checked)
                      </Text>
                    </View>

                    <View style={styles.checkItemRow}>
                      <MaterialIcons name="cancel" size={18} color={colors.secondary} />
                      <Text style={styles.checkItemText}>
                        AI analysis pending — starts automatically when connection is restored
                      </Text>
                    </View>
                  </View>
                </View>
              )}

              {/* Action buttons */}
              {!syncing && (
                <View style={styles.actionsContainer}>
                  {/* Manual Retry — fallback only */}
                  <TouchableOpacity
                    style={styles.retryButton}
                    onPress={handleRetryConnection}
                    disabled={syncing}
                    activeOpacity={0.85}
                  >
                    <MaterialIcons name="sync" size={18} color={colors.onPrimary} />
                    <Text style={styles.retryButtonText}>Retry Connection</Text>
                  </TouchableOpacity>

                  {currentDraft && isPendingSync(currentDraft.status) && (
                    <TouchableOpacity
                      style={styles.continueOfflineBtn}
                      onPress={() =>
                        navigation.navigate('CaptureImages', {
                          inspectionId: currentDraft.clientDraftId,
                          inspectionNumber: undefined,
                        })
                      }
                      activeOpacity={0.85}
                    >
                      <Text style={styles.continueOfflineText}>Continue Capturing Offline</Text>
                    </TouchableOpacity>
                  )}

                  <Text style={styles.autoSyncNote}>
                    Sync starts automatically when the connection is restored — no action required.
                  </Text>
                </View>
              )}
            </>
          ) : (
            /* Online State with All Synced */
            <View style={styles.onlineContainer}>
              <View style={styles.onlineBadge}>
                <MaterialIcons name="cloud-done" size={20} color={colors.statusGreenText} />
                <Text style={styles.onlineBadgeText}>Online — Central Server Connected</Text>
              </View>

              <View style={styles.centralCard}>
                <View style={styles.centralCardHeader}>
                  <MaterialIcons name="check-circle" size={20} color={colors.statusGreenText} />
                  <Text style={styles.centralCardHeaderText}>INSPECTIONS SYNCHRONIZED</Text>
                </View>

                <View style={styles.centralCardBody}>
                  <Text style={{ ...typography.bodyMd, color: colors.onSurface, lineHeight: 20 }}>
                    All package commodity inspections are synchronized with NiriKsha Central Server.
                  </Text>
                  <Text style={{ ...typography.bodySm, color: colors.onSurfaceVariant, marginTop: 4 }}>
                    New inspections created will be processed with deterministic Legal Metrology (Packaged Commodities) Rules 2011 evaluations.
                  </Text>
                </View>
              </View>

              <View style={styles.actionsContainer}>
                <TouchableOpacity
                  style={styles.retryButton}
                  onPress={() => navigation.navigate('NewInspection')}
                  activeOpacity={0.85}
                >
                  <MaterialIcons name="add-circle" size={18} color={colors.onPrimary} />
                  <Text style={styles.retryButtonText}>Start New Inspection</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.continueOfflineBtn}
                  onPress={() => navigation.navigate('Dashboard')}
                  activeOpacity={0.85}
                >
                  <Text style={styles.continueOfflineText}>Return to Dashboard</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}
        </ScrollView>

        {/* Bottom Navigation */}
        <BottomNav />
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.background },
  container: { flex: 1, backgroundColor: colors.background },
  topHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.surfaceContainerLowest,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    height: 56,
    paddingHorizontal: spacing.gutter,
  },
  backButton: { padding: 6, borderRadius: borderRadius.round },
  headerTitle: {
    ...typography.headlineLg,
    fontSize: 18,
    fontWeight: '700',
    color: colors.primary,
  },
  warningBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.statusAmberBg,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    paddingHorizontal: spacing.gutter,
    paddingVertical: spacing.stackSm,
    gap: 8,
  },
  warningBannerText: {
    ...typography.bodySm,
    fontSize: 13,
    fontWeight: '600',
    color: colors.statusAmberText,
  },
  onlineSyncBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.statusGreenBg,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    paddingHorizontal: spacing.gutter,
    paddingVertical: spacing.stackSm,
    gap: 8,
  },
  onlineSyncBannerText: {
    ...typography.bodySm,
    fontSize: 13,
    fontWeight: '600',
    color: colors.statusGreenText,
  },
  scrollContent: {
    paddingHorizontal: spacing.gutter,
    paddingTop: spacing.stackMd,
    paddingBottom: 90,
    gap: spacing.stackMd,
  },
  instructionText: {
    ...typography.bodyMd,
    fontSize: 14,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
  },
  // Sync progress card
  syncProgressCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.primary,
    borderRadius: borderRadius.DEFAULT,
    padding: spacing.gutter,
    gap: 12,
  },
  syncProgressCardError: {
    borderColor: colors.statusAmberText,
  },
  syncProgressHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingBottom: spacing.stackSm,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  syncProgressTitle: {
    ...typography.sectionHeader,
    fontSize: 15,
    fontWeight: '700',
    color: colors.primary,
  },
  syncProgressTitleError: {
    color: colors.statusAmberText,
  },
  syncSteps: { gap: 8 },
  syncStepRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  syncStepText: {
    ...typography.bodySm,
    fontSize: 13,
    color: colors.secondary,
  },
  syncStepTextDone: { color: colors.statusGreenText, fontWeight: '500' },
  syncStepTextActive: { color: colors.primary, fontWeight: '600' },
  syncErrorNote: {
    ...typography.caption,
    fontSize: 11,
    color: colors.statusAmberText,
    marginTop: 4,
  },
  // Draft info card
  centralCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    padding: spacing.gutter,
    gap: 12,
  },
  centralCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    paddingBottom: spacing.stackSm,
  },
  centralCardHeaderText: {
    ...typography.sectionHeader,
    fontSize: 14,
    color: colors.onSurface,
    fontWeight: '700',
  },
  centralCardBody: { gap: 8 },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  infoLabel: { ...typography.bodyMd, fontSize: 13, color: colors.onSurfaceVariant },
  infoValueBold: { ...typography.bodyMd, fontSize: 14, fontWeight: '600', color: colors.onSurface },
  cardFooterRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
    marginTop: 4,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: colors.surfaceContainerHigh,
  },
  imagesSavedBox: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  imagesSavedText: { ...typography.caption, fontSize: 11, color: colors.onSurfaceVariant },
  pendingBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.statusAmberBg,
    borderWidth: 1,
    borderColor: colors.statusAmberText,
    borderRadius: borderRadius.DEFAULT,
    paddingHorizontal: 8,
    paddingVertical: 2,
    gap: 4,
  },
  pendingBadgeText: {
    ...typography.labelCaps,
    fontSize: 10,
    fontWeight: '600',
    color: colors.statusAmberText,
  },
  // Checklist card
  checklistCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    padding: spacing.gutter,
    gap: 10,
  },
  checklistTitle: {
    ...typography.sectionHeader,
    fontSize: 14,
    color: colors.onSurface,
    fontWeight: '600',
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    paddingBottom: spacing.stackSm,
  },
  checklistItemsList: { gap: 10 },
  checkItemRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  checkItemText: { ...typography.bodySm, fontSize: 13, color: colors.onSurfaceVariant, flex: 1 },
  // Actions
  actionsContainer: { gap: 10, marginTop: 4 },
  retryButton: {
    backgroundColor: colors.primaryContainer,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: borderRadius.DEFAULT,
    gap: 8,
  },
  retryButtonText: {
    ...typography.sectionHeader,
    fontSize: 14,
    color: colors.onPrimary,
    fontWeight: '600',
  },
  continueOfflineBtn: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: colors.primaryContainer,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: borderRadius.DEFAULT,
  },
  continueOfflineText: {
    ...typography.sectionHeader,
    fontSize: 14,
    color: colors.primaryContainer,
    fontWeight: '600',
  },
  autoSyncNote: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
    marginTop: 4,
  },
  // Online state
  onlineContainer: { gap: spacing.stackMd },
  onlineBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.statusGreenBg,
    borderWidth: 1,
    borderColor: colors.statusGreenText,
    borderRadius: borderRadius.DEFAULT,
    paddingVertical: 8,
    paddingHorizontal: 12,
    gap: 8,
  },
  onlineBadgeText: {
    ...typography.bodySm,
    fontSize: 13,
    fontWeight: '600',
    color: colors.statusGreenText,
  },
});
