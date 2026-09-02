import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  SafeAreaView,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { BottomNav } from '../components/BottomNav';
import { ProfileAvatar } from '../components/ProfileAvatar';
import { useNavigation, useRoute, RouteProp, useFocusEffect } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';
import { networkService, ConnectivityState } from '../services/networkService';
import { draftStorage, LocalDraft } from '../services/draftStorage';
import { syncService } from '../services/syncService';

export const DraftOfflineScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'DraftOffline'>>();
  const paramDraftId = route.params?.clientDraftId;

  const [networkState, setNetworkState] = useState<ConnectivityState>(networkService.getState());
  const [currentDraft, setCurrentDraft] = useState<LocalDraft | null>(null);
  const [allDrafts, setAllDrafts] = useState<LocalDraft[]>([]);
  const [retrying, setRetrying] = useState(false);
  const [loading, setLoading] = useState(true);

  const updateDraftSelection = (drafts: LocalDraft[]) => {
    setAllDrafts(drafts);
    if (paramDraftId) {
      const found = drafts.find((d) => d.clientDraftId === paramDraftId);
      if (found) {
        setCurrentDraft(found);
        return;
      }
    }
    const pending = drafts.find((d) => d.status === 'PENDING_SYNC' || d.status === 'LOCAL_DRAFT');
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

  const handleRetryConnection = async () => {
    setRetrying(true);
    try {
      const isOnline = await networkService.checkReachability();
      if (!isOnline) {
        Alert.alert(
          'Connection Unavailable',
          'Could not reach NiriKsha Central Server. Your draft remains safely stored on this device.'
        );
        return;
      }

      if (currentDraft && currentDraft.status !== 'SYNCED') {
        try {
          const syncedInspection = await syncService.syncDraft(currentDraft);
          await loadDraftData();
          Alert.alert(
            'Synchronization Successful',
            `Connection restored. Inspection ${syncedInspection.inspection_number} has been created and synchronized with the Central Server.`,
            [
              {
                text: 'View Inspection',
                onPress: () =>
                  navigation.navigate('CaptureImages', {
                    inspectionId: syncedInspection.id,
                    inspectionNumber: syncedInspection.inspection_number,
                  }),
              },
              {
                text: 'Go to Dashboard',
                onPress: () => navigation.navigate('Dashboard'),
              },
            ]
          );
        } catch (syncErr: any) {
          Alert.alert('Sync Incomplete', syncErr.message || 'Server reached, but sync could not be completed.');
        }
      } else {
        Alert.alert(
          'Connection Restored',
          'NiriKsha Central Server is online and ready for inspections.',
          [{ text: 'OK', onPress: () => navigation.navigate('Dashboard') }]
        );
      }
    } finally {
      setRetrying(false);
    }
  };

  const isOffline = networkState === 'OFFLINE';
  const hasPendingDraft = currentDraft && (currentDraft.status === 'PENDING_SYNC' || currentDraft.status === 'LOCAL_DRAFT');
  const showOfflineUI = isOffline || Boolean(hasPendingDraft);


  const dateStr = currentDraft?.createdAt
    ? new Date(currentDraft.createdAt).toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
    : new Date().toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      });

  const displayDraftId = currentDraft?.clientDraftId
    ? currentDraft.clientDraftId.length > 20
      ? `${currentDraft.clientDraftId.substring(0, 16)}...`
      : currentDraft.clientDraftId
    : 'draft-offline';

  return (
    <SafeAreaView style={styles.safeArea}>
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

        {/* Warning Banner — Only shown when OFFLINE */}
        {isOffline && (
          <View style={styles.warningBanner}>
            <MaterialIcons name="warning" size={18} color={colors.statusAmberText} />
            <Text style={styles.warningBannerText}>Connection Lost</Text>
          </View>
        )}

        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          {loading ? (
            <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
          ) : showOfflineUI ? (

            <>
              {/* Header Text */}
              <Text style={styles.instructionText}>
                {hasPendingDraft
                  ? 'Your inspection has been saved as a local draft.'
                  : 'Operating in offline mode. Local drafts will sync when connectivity returns.'}
              </Text>

              {/* Central Card */}
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
                      {currentDraft?.productName || 'Basmati Rice (Draft)'}
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
                        {currentDraft?.status === 'SYNCED' ? 'SYNCED' : 'DRAFT — Pending Sync'}
                      </Text>
                    </View>
                  </View>
                </View>
              </View>

              {/* Checklist Card */}
              <View style={styles.checklistCard}>
                <Text style={styles.checklistTitle}>What was saved:</Text>

                <View style={styles.checklistItemsList}>
                  <View style={styles.checkItemRow}>
                    <MaterialIcons name="check-circle" size={18} color={colors.statusGreenText} />
                    <Text style={styles.checkItemText}>Inspection details</Text>
                  </View>

                  <View style={styles.checkItemRow}>
                    <MaterialIcons name="check-circle" size={18} color={colors.statusGreenText} />
                    <Text style={styles.checkItemText}>
                      {currentDraft?.images?.length || 0} package images (locally stored)
                    </Text>
                  </View>

                  <View style={styles.checkItemRow}>
                    <MaterialIcons name="cancel" size={18} color={colors.statusRedText} />
                    <Text style={styles.checkItemText}>AI analysis not started (requires connection)</Text>
                  </View>
                </View>
              </View>

              {/* Action Buttons */}
              <View style={styles.actionsContainer}>
                <TouchableOpacity
                  style={styles.retryButton}
                  onPress={handleRetryConnection}
                  disabled={retrying}
                  activeOpacity={0.85}
                >
                  {retrying ? (
                    <ActivityIndicator size="small" color={colors.onPrimary} />
                  ) : (
                    <>
                      <MaterialIcons name="sync" size={18} color={colors.onPrimary} />
                      <Text style={styles.retryButtonText}>Retry Connection</Text>
                    </>
                  )}
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.continueOfflineBtn}
                  onPress={() => navigation.navigate('NewInspection')}
                  activeOpacity={0.85}
                >
                  <Text style={styles.continueOfflineText}>Continue Offline — Review Draft</Text>
                </TouchableOpacity>

                <Text style={styles.autoSyncNote}>
                  Your data will sync automatically when the connection is restored.
                </Text>
              </View>
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
  safeArea: {
    flex: 1,
    backgroundColor: colors.background,
  },
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
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
  backButton: {
    padding: 6,
    borderRadius: borderRadius.round,
  },
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
  centralCardBody: {
    gap: 8,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  infoLabel: {
    ...typography.bodyMd,
    fontSize: 13,
    color: colors.onSurfaceVariant,
  },
  infoValueBold: {
    ...typography.bodyMd,
    fontSize: 14,
    fontWeight: '600',
    color: colors.onSurface,
  },
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
  imagesSavedBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  imagesSavedText: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
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
  checklistItemsList: {
    gap: 10,
  },
  checkItemRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  checkItemText: {
    ...typography.bodySm,
    fontSize: 13,
    color: colors.onSurfaceVariant,
  },
  actionsContainer: {
    gap: 10,
    marginTop: 4,
  },
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
  onlineContainer: {
    gap: spacing.stackMd,
  },
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
