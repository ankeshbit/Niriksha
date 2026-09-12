import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  RefreshControl,
  ActivityIndicator,
  Platform,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { BottomNav, BOTTOM_NAV_TAB_HEIGHT } from '../components/BottomNav';
import { ProfileAvatar } from '../components/ProfileAvatar';
import { api } from '../services/api';
import { networkService, ConnectivityState } from '../services/networkService';
import { draftStorage, LocalDraft, isPendingSync } from '../services/draftStorage';
import { syncService } from '../services/syncService';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

// Filter Chip Definitions for Inspection Registry
interface FilterChip {
  id: string;
  label: string;
  matcher?: (item: any) => boolean;
}

const INSPECTION_FILTER_CHIPS: FilterChip[] = [
  { id: 'all', label: 'All' },
  {
    id: 'needs_verification',
    label: 'Needs Verification',
    matcher: (i) => (i.overall_status || '').toUpperCase() === 'NEEDS_MANUAL_VERIFICATION',
  },
  {
    id: 'potential_non_compliance',
    label: 'Potential Non-Compliance',
    matcher: (i) =>
      ['POTENTIAL_NON_COMPLIANCE', 'FAIL', 'CONFIRMED'].includes(
        (i.overall_status || '').toUpperCase()
      ),
  },
  {
    id: 'compliant',
    label: 'Compliant',
    matcher: (i) =>
      ['NO_POTENTIAL_VIOLATIONS', 'VERIFIED_COMPLIANT', 'PASS'].includes(
        (i.overall_status || '').toUpperCase()
      ),
  },
  {
    id: 'completed',
    label: 'Completed',
    matcher: (i) => ['COMPLETED', 'FINALIZED'].includes((i.status || '').toUpperCase()),
  },
];

export const InspectionsScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const insets = useSafeAreaInsets();

  // Connectivity & Draft States
  const [networkState, setNetworkState] = useState<ConnectivityState>(networkService.getState());
  const [isResolvingConnectivity, setIsResolvingConnectivity] = useState(networkState === 'UNKNOWN');
  const [allDrafts, setAllDrafts] = useState<LocalDraft[]>([]);
  const [isSyncingDrafts, setIsSyncingDrafts] = useState(false);

  // Data & List States
  const [inspections, setInspections] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedChipId, setSelectedChipId] = useState<string>('all');
  const [retrying, setRetrying] = useState(false);

  const isSyncInProgressRef = useRef(false);

  // Pending drafts needing synchronization
  const pendingDrafts = allDrafts.filter((d) => isPendingSync(d.status));

  // ─── 1. Load Data ──────────────────────────────────────────────────────────

  const loadDrafts = async () => {
    try {
      const drafts = await draftStorage.getDrafts();
      setAllDrafts(drafts);
    } catch (e) {
      console.warn('[InspectionsScreen] loadDrafts error:', e);
    }
  };

  const loadInspections = async (silent = false) => {
    try {
      const resp = await api.getDashboardInspections({ limit: 100 });
      setInspections(resp?.items || []);
    } catch (err) {
      if (!silent) {
        console.error('[InspectionsScreen] loadInspections error:', err);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  // ─── 2. Background Sync ────────────────────────────────────────────────────

  const triggerBackgroundSync = useCallback(async () => {
    if (isSyncInProgressRef.current) return;
    const drafts = await draftStorage.getDrafts();
    const pending = drafts.filter((d) => isPendingSync(d.status));
    if (pending.length === 0) return;

    isSyncInProgressRef.current = true;
    setIsSyncingDrafts(true);

    try {
      await syncService.syncAllPendingDrafts();
      await loadDrafts();
      await loadInspections(true);
    } catch (e) {
      console.warn('[InspectionsScreen] background sync error:', e);
    } finally {
      isSyncInProgressRef.current = false;
      setIsSyncingDrafts(false);
    }
  }, []);

  // ─── 3. Screen Focus & Connectivity Resolution ─────────────────────────────

  useFocusEffect(
    useCallback(() => {
      let isMounted = true;

      const resolveAndFetch = async () => {
        // Resolve connectivity dynamically
        const isOnline = await networkService.checkReachability();
        if (!isMounted) return;

        const resolvedState: ConnectivityState = isOnline ? 'ONLINE' : 'OFFLINE';
        setNetworkState(resolvedState);
        setIsResolvingConnectivity(false);

        // Load local drafts in all cases
        await loadDrafts();

        if (isOnline) {
          // Fetch live inspections
          await loadInspections();
          // Trigger background sync if pending drafts exist
          triggerBackgroundSync();
        } else {
          setLoading(false);
        }
      };

      resolveAndFetch();

      return () => {
        isMounted = false;
      };
    }, [triggerBackgroundSync])
  );

  // ─── 4. Subscriptions (Network & Reconnect) ─────────────────────────────────

  useEffect(() => {
    const unsubNetwork = networkService.subscribe((state) => {
      setNetworkState(state);
      if (state !== 'UNKNOWN') {
        setIsResolvingConnectivity(false);
      }
      if (state === 'ONLINE') {
        loadInspections(true);
        triggerBackgroundSync();
      }
    });

    const unsubDrafts = draftStorage.subscribe((drafts) => {
      setAllDrafts(drafts);
    });

    const unsubReconnect = networkService.onReconnect(() => {
      setNetworkState('ONLINE');
      setIsResolvingConnectivity(false);
      loadInspections(true);
      triggerBackgroundSync();
    });

    return () => {
      unsubNetwork();
      unsubDrafts();
      unsubReconnect();
    };
  }, [triggerBackgroundSync]);

  // ─── 5. Refresh & Retry Handlers ───────────────────────────────────────────

  const onRefresh = async () => {
    setRefreshing(true);
    const isOnline = await networkService.checkReachability();
    setNetworkState(isOnline ? 'ONLINE' : 'OFFLINE');
    await loadDrafts();
    if (isOnline) {
      await loadInspections(true);
      triggerBackgroundSync();
    } else {
      setRefreshing(false);
    }
  };

  const handleManualRetry = async () => {
    setRetrying(true);
    try {
      const isOnline = await networkService.checkReachability();
      const resolved = isOnline ? 'ONLINE' : 'OFFLINE';
      setNetworkState(resolved);
      if (isOnline) {
        setLoading(true);
        await loadDrafts();
        await loadInspections();
        triggerBackgroundSync();
      }
    } finally {
      setRetrying(false);
    }
  };

  // ─── 6. Filtering ──────────────────────────────────────────────────────────

  const filteredInspections = inspections.filter((item) => {
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchNum = (item.inspection_number || '').toLowerCase().includes(q);
      const matchProd = (item.product_name || '').toLowerCase().includes(q);
      const matchBrand = (item.brand_name || '').toLowerCase().includes(q);
      const matchLoc = (item.location || '').toLowerCase().includes(q);
      if (!matchNum && !matchProd && !matchBrand && !matchLoc) return false;
    }

    if (selectedChipId && selectedChipId !== 'all') {
      const chip = INSPECTION_FILTER_CHIPS.find((c) => c.id === selectedChipId);
      if (chip?.matcher && !chip.matcher(item)) return false;
    }

    return true;
  });

  const getStatusBadgeProps = (status?: string) => {
    const s = (status || '').toUpperCase();
    if (s === 'POTENTIAL_NON_COMPLIANCE' || s === 'FAIL' || s === 'CONFIRMED') {
      return {
        label: 'Potential Non-Compliance',
        bg: colors.statusRedBg,
        text: colors.statusRedText,
        border: 'rgba(183, 28, 28, 0.25)',
      };
    }
    if (s === 'VERIFIED_COMPLIANT' || s === 'NO_POTENTIAL_VIOLATIONS' || s === 'PASS') {
      return {
        label: 'Verified Compliant',
        bg: colors.statusGreenBg,
        text: colors.statusGreenText,
        border: 'rgba(27, 94, 32, 0.25)',
      };
    }
    if (s === 'NEEDS_MANUAL_VERIFICATION' || s === 'WARNING') {
      return {
        label: 'Needs Verification',
        bg: colors.statusAmberBg,
        text: colors.statusAmberText,
        border: 'rgba(230, 81, 0, 0.25)',
      };
    }
    if (s === 'INSUFFICIENT_EVIDENCE') {
      return {
        label: 'Insufficient Evidence',
        bg: colors.surfaceContainerHighest,
        text: colors.onSurface,
        border: colors.borderSubtle,
      };
    }
    return {
      label: status ? status.replace(/_/g, ' ') : 'Under Review',
      bg: colors.surfaceContainerLow,
      text: colors.onSurfaceVariant,
      border: colors.borderSubtle,
    };
  };

  const handleInspectionPress = (item: any) => {
    if (item.status === 'COMPLETED' || item.has_report) {
      navigation.navigate('ReportPreview', {
        inspectionId: item.id,
        inspectionNumber: item.inspection_number,
      });
    } else if (item.status === 'RULE_EVALUATION_COMPLETE' || item.overall_status) {
      navigation.navigate('Findings', {
        inspectionId: item.id,
        inspectionNumber: item.inspection_number,
      });
    } else {
      navigation.navigate('ExtractedDeclarations', {
        inspectionId: item.id,
        inspectionNumber: item.inspection_number,
      });
    }
  };

  const isActuallyOffline = networkState === 'OFFLINE';

  // ─── 7. Render ─────────────────────────────────────────────────────────────

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
      <View style={styles.container}>
        {/* Top Header */}
        <View style={styles.topHeader}>
          <TouchableOpacity
            style={styles.headerIconButton}
            onPress={() => navigation.navigate('Dashboard')}
            activeOpacity={0.7}
            accessibilityRole="button"
            accessibilityLabel="Go to Dashboard"
          >
            <MaterialIcons name="menu" size={24} color={colors.onSurfaceVariant} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>NiriKsha</Text>
          <TouchableOpacity
            style={styles.headerIconButton}
            onPress={() => navigation.navigate('Profile')}
            activeOpacity={0.7}
            accessibilityRole="button"
            accessibilityLabel="Open Profile"
          >
            <ProfileAvatar size={34} />
          </TouchableOpacity>
        </View>

        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={[
            styles.scrollContent,
            { paddingBottom: BOTTOM_NAV_TAB_HEIGHT + Math.max(insets.bottom, 6) + 20 },
          ]}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
          showsVerticalScrollIndicator={false}
        >
          {/* Page Title & Status Header */}
          <View style={styles.pageHeader}>
            <View style={{ flex: 1 }}>
              <Text style={styles.pageTitle}>Inspection Registry</Text>
              <Text style={styles.pageSubtitle}>
                Official Legal Metrology (Packaged Commodities) inspection records
              </Text>
            </View>

            {/* Live Connectivity Badge */}
            <View
              style={[
                styles.connBadge,
                isActuallyOffline
                  ? styles.connBadgeOffline
                  : networkState === 'ONLINE'
                  ? styles.connBadgeOnline
                  : styles.connBadgeChecking,
              ]}
            >
              <MaterialIcons
                name={
                  isActuallyOffline
                    ? 'cloud-off'
                    : networkState === 'ONLINE'
                    ? 'cloud-done'
                    : 'cloud-sync'
                }
                size={14}
                color={
                  isActuallyOffline
                    ? colors.statusRedText
                    : networkState === 'ONLINE'
                    ? colors.statusGreenText
                    : colors.onSurfaceVariant
                }
              />
              <Text
                style={[
                  styles.connBadgeText,
                  {
                    color: isActuallyOffline
                      ? colors.statusRedText
                      : networkState === 'ONLINE'
                      ? colors.statusGreenText
                      : colors.onSurfaceVariant,
                  },
                ]}
              >
                {isActuallyOffline
                  ? 'Offline Mode'
                  : networkState === 'ONLINE'
                  ? 'Central Server'
                  : 'Resolving...'}
              </Text>
            </View>
          </View>

          {/* ── UNKNOWN / RESOLVING STATE ── */}
          {isResolvingConnectivity && loading ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color={colors.primary} />
              <Text style={styles.loadingText}>Verifying server connectivity...</Text>
            </View>
          ) : isActuallyOffline ? (
            /* ── OFFLINE WORKFLOW STATE ── */
            <View style={styles.offlineWorkflowContainer}>
              {/* Offline Banner */}
              <View style={styles.offlineBanner}>
                <MaterialIcons name="wifi-off" size={24} color={colors.statusAmberText} />
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={styles.offlineBannerTitle}>Operating in Offline Mode</Text>
                  <Text style={styles.offlineBannerSubtitle}>
                    NiriKsha Central Server is currently unreachable. You can continue capturing
                    commodities locally. Drafts will synchronize automatically once connectivity is
                    restored.
                  </Text>
                </View>
              </View>

              {/* Action Buttons Row */}
              <View style={styles.offlineActionsRow}>
                <TouchableOpacity
                  style={styles.retryBtn}
                  onPress={handleManualRetry}
                  disabled={retrying}
                  activeOpacity={0.8}
                >
                  {retrying ? (
                    <ActivityIndicator size="small" color={colors.onPrimary} />
                  ) : (
                    <>
                      <MaterialIcons name="refresh" size={18} color={colors.onPrimary} />
                      <Text style={styles.retryBtnText}>Retry Connection</Text>
                    </>
                  )}
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.captureOfflineBtn}
                  onPress={() => navigation.navigate('NewInspection')}
                  activeOpacity={0.8}
                >
                  <MaterialIcons name="add-a-photo" size={18} color={colors.primary} />
                  <Text style={styles.captureOfflineBtnText}>New Offline Capture</Text>
                </TouchableOpacity>
              </View>

              {/* Locally Stored Drafts Section */}
              <View style={styles.sectionHeaderRow}>
                <Text style={styles.sectionTitle}>
                  Locally Saved Drafts ({allDrafts.length})
                </Text>
              </View>

              {allDrafts.length === 0 ? (
                <View style={styles.emptyDraftsCard}>
                  <MaterialIcons name="folder-open" size={36} color={colors.onSurfaceVariant} />
                  <Text style={styles.emptyDraftsTitle}>No Offline Drafts</Text>
                  <Text style={styles.emptyDraftsSubtitle}>
                    Any commodity inspections captured while offline will appear here until synced.
                  </Text>
                </View>
              ) : (
                allDrafts.map((draft) => {
                  const isPending = isPendingSync(draft.status);
                  const dateStr = draft.createdAt
                    ? new Date(draft.createdAt).toLocaleDateString('en-GB', {
                        day: 'numeric',
                        month: 'short',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })
                    : 'Saved offline';

                  return (
                    <View key={draft.clientDraftId} style={styles.draftCard}>
                      <View style={styles.draftCardTop}>
                        <View style={{ flex: 1 }}>
                          <Text style={styles.draftIdText} numberOfLines={1}>
                            {draft.syncedInspectionNumber || draft.clientDraftId}
                          </Text>
                          <Text style={styles.draftProductText}>
                            {draft.productName || 'Packaged Commodity'}
                          </Text>
                          <Text style={styles.draftDateText}>{dateStr}</Text>
                        </View>
                        <View
                          style={[
                            styles.draftBadge,
                            isPending ? styles.draftBadgePending : styles.draftBadgeSynced,
                          ]}
                        >
                          <Text
                            style={[
                              styles.draftBadgeText,
                              {
                                color: isPending
                                  ? colors.statusAmberText
                                  : colors.statusGreenText,
                              },
                            ]}
                          >
                            {isPending ? 'PENDING SYNC' : 'SYNCED'}
                          </Text>
                        </View>
                      </View>

                      <View style={styles.draftCardBottom}>
                        <View style={styles.draftImagesCount}>
                          <MaterialIcons name="photo-camera" size={14} color={colors.onSurfaceVariant} />
                          <Text style={styles.draftImagesText}>
                            {draft.images?.length || 0} images captured
                          </Text>
                        </View>

                        {isPending && (
                          <TouchableOpacity
                            style={styles.continueCaptureBtn}
                            onPress={() =>
                              navigation.navigate('CaptureImages', {
                                inspectionId: draft.clientDraftId,
                                inspectionNumber: draft.syncedInspectionNumber,
                              })
                            }
                            activeOpacity={0.8}
                          >
                            <Text style={styles.continueCaptureBtnText}>Continue Capturing</Text>
                            <MaterialIcons name="chevron-right" size={16} color={colors.primary} />
                          </TouchableOpacity>
                        )}
                      </View>
                    </View>
                  );
                })
              )}
            </View>
          ) : (
            /* ── ONLINE INSPECTION REGISTRY STATE ── */
            <View style={{ gap: 14 }}>
              {/* NON-BLOCKING PENDING SYNC BANNER */}
              {pendingDrafts.length > 0 && (
                <View style={styles.syncBannerCard}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
                    {isSyncingDrafts ? (
                      <ActivityIndicator size="small" color={colors.primary} />
                    ) : (
                      <MaterialIcons name="cloud-upload" size={24} color={colors.primary} />
                    )}
                    <View style={{ flex: 1 }}>
                      <Text style={styles.syncBannerTitle}>
                        {isSyncingDrafts
                          ? 'Synchronizing Offline Drafts...'
                          : `${pendingDrafts.length} Local Draft(s) Ready to Sync`}
                      </Text>
                      <Text style={styles.syncBannerSubtitle}>
                        {isSyncingDrafts
                          ? 'Uploading captured evidence to NiriKsha Central Server in the background.'
                          : 'Central Server connected. Syncing automatically with live registry.'}
                      </Text>
                    </View>
                  </View>

                  {!isSyncingDrafts && (
                    <TouchableOpacity
                      style={styles.syncNowBtn}
                      onPress={triggerBackgroundSync}
                      activeOpacity={0.8}
                    >
                      <Text style={styles.syncNowBtnText}>Sync Now</Text>
                    </TouchableOpacity>
                  )}
                </View>
              )}

              {/* Search Box */}
              <View style={styles.searchRow}>
                <MaterialIcons name="search" size={20} color={colors.onSurfaceVariant} />
                <TextInput
                  style={styles.searchInput}
                  value={searchQuery}
                  onChangeText={setSearchQuery}
                  placeholder="Search by ID, product, brand, or location..."
                  placeholderTextColor={colors.onSurfaceVariant}
                  returnKeyType="search"
                />
                {searchQuery ? (
                  <TouchableOpacity onPress={() => setSearchQuery('')}>
                    <MaterialIcons name="cancel" size={18} color={colors.onSurfaceVariant} />
                  </TouchableOpacity>
                ) : null}
              </View>

              {/* Filter Chips Horizontal Scroll */}
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={styles.filterChipScroll}
              >
                {INSPECTION_FILTER_CHIPS.map((chip) => {
                  const isSelected = selectedChipId === chip.id;
                  return (
                    <TouchableOpacity
                      key={chip.id}
                      style={[styles.filterChip, isSelected && styles.filterChipSelected]}
                      onPress={() => setSelectedChipId(chip.id)}
                      activeOpacity={0.7}
                    >
                      <Text
                        style={[
                          styles.filterChipText,
                          isSelected && styles.filterChipTextSelected,
                        ]}
                      >
                        {chip.label}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </ScrollView>

              {/* Total Count Header */}
              <View style={styles.countRow}>
                <Text style={styles.countText}>
                  Showing {filteredInspections.length} inspection(s)
                </Text>
                <TouchableOpacity
                  style={styles.newInspectionSmallBtn}
                  onPress={() => navigation.navigate('NewInspection')}
                  activeOpacity={0.8}
                >
                  <MaterialIcons name="add" size={16} color={colors.onPrimary} />
                  <Text style={styles.newInspectionSmallBtnText}>New Inspection</Text>
                </TouchableOpacity>
              </View>

              {/* Inspections List */}
              {loading && !refreshing ? (
                <View style={styles.loadingContainer}>
                  <ActivityIndicator size="large" color={colors.primary} />
                  <Text style={styles.loadingText}>Loading inspection registry...</Text>
                </View>
              ) : filteredInspections.length === 0 ? (
                <View style={styles.emptyContainer}>
                  <MaterialIcons name="search-off" size={44} color={colors.onSurfaceVariant} />
                  <Text style={styles.emptyTitle}>No Inspections Found</Text>
                  <Text style={styles.emptySubtitle}>
                    {searchQuery
                      ? 'No inspection records match your current search or filter criteria.'
                      : 'No statutory inspections recorded yet. Tap "+ New Inspection" to begin.'}
                  </Text>
                </View>
              ) : (
                <View style={styles.cardContainer}>
                  {filteredInspections.map((item, idx) => {
                    const isLast = idx === filteredInspections.length - 1;
                    const badge = getStatusBadgeProps(item.overall_status || item.status);
                    const dateStr = item.created_at
                      ? new Date(item.created_at).toLocaleDateString('en-GB', {
                          day: 'numeric',
                          month: 'short',
                          year: 'numeric',
                        })
                      : 'Recent';

                    return (
                      <TouchableOpacity
                        key={item.id || idx}
                        style={[styles.inspectionRow, !isLast && styles.rowBorder]}
                        onPress={() => handleInspectionPress(item)}
                        activeOpacity={0.7}
                      >
                        <View style={styles.rowTop}>
                          <View style={{ flex: 1 }}>
                            <Text style={styles.rowInspNumber}>
                              {item.inspection_number || item.id}
                            </Text>
                            <Text style={styles.rowDate}>{dateStr}</Text>
                          </View>
                          <View
                            style={[
                              styles.statusBadge,
                              { backgroundColor: badge.bg, borderColor: badge.border },
                            ]}
                          >
                            <Text style={[styles.statusBadgeText, { color: badge.text }]}>
                              {badge.label}
                            </Text>
                          </View>
                        </View>

                        <Text style={styles.rowProductName} numberOfLines={1}>
                          {item.product_name || 'Packaged Commodity'}
                        </Text>

                        <View style={styles.rowMeta}>
                          {item.brand_name ? (
                            <Text style={styles.rowBrand} numberOfLines={1}>
                              Brand: {item.brand_name}
                            </Text>
                          ) : null}
                          <View style={styles.rowLocationBox}>
                            <MaterialIcons name="place" size={13} color={colors.onSurfaceVariant} />
                            <Text style={styles.rowLocation} numberOfLines={1}>
                              {item.location || 'Field Location'}
                            </Text>
                          </View>
                        </View>

                        <View style={styles.rowBottomActions}>
                          <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                            {item.has_report && (
                              <View style={styles.reportBadge}>
                                <MaterialIcons name="description" size={12} color={colors.primary} />
                                <Text style={styles.reportBadgeText}>PDF Report</Text>
                              </View>
                            )}
                            {item.pending_actions_count > 0 && (
                              <View style={styles.warningBadge}>
                                <MaterialIcons
                                  name="priority-high"
                                  size={12}
                                  color={colors.statusAmberText}
                                />
                                <Text style={styles.warningBadgeText}>
                                  {item.pending_actions_count} Action(s)
                                </Text>
                              </View>
                            )}
                          </View>

                          <View style={styles.viewArrowRow}>
                            <Text style={styles.viewArrowText}>View Details</Text>
                            <MaterialIcons name="chevron-right" size={16} color={colors.primary} />
                          </View>
                        </View>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              )}
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
  headerIconButton: {
    padding: 6,
    borderRadius: borderRadius.round,
  },
  headerTitle: {
    ...typography.headlineLg,
    fontSize: 20,
    fontWeight: '800',
    color: colors.primary,
    letterSpacing: -0.3,
  },
  scrollContent: {
    padding: spacing.gutter,
    gap: 14,
  },
  pageHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
    marginBottom: 4,
  },
  pageTitle: {
    ...typography.headlineLg,
    fontSize: 20,
    fontWeight: '700',
    color: colors.onSurface,
  },
  pageSubtitle: {
    ...typography.bodySm,
    fontSize: 12,
    color: colors.onSurfaceVariant,
    marginTop: 2,
  },
  connBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: borderRadius.round,
    borderWidth: 1,
  },
  connBadgeOnline: {
    backgroundColor: colors.statusGreenBg,
    borderColor: 'rgba(27, 94, 32, 0.2)',
  },
  connBadgeOffline: {
    backgroundColor: colors.statusRedBg,
    borderColor: 'rgba(183, 28, 28, 0.2)',
  },
  connBadgeChecking: {
    backgroundColor: colors.surfaceContainerHigh,
    borderColor: colors.borderSubtle,
  },
  connBadgeText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
  },
  loadingContainer: {
    paddingVertical: 50,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  loadingText: {
    ...typography.bodySm,
    color: colors.onSurfaceVariant,
  },

  // ─── Sync Banner Card ───────────────────────────────────────────────────────
  syncBannerCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: 'rgba(2, 132, 199, 0.08)',
    borderWidth: 1,
    borderColor: 'rgba(2, 132, 199, 0.25)',
    borderRadius: borderRadius.xl,
    padding: 12,
    gap: 10,
  },
  syncBannerTitle: {
    ...typography.bodyMd,
    fontSize: 13,
    fontWeight: '700',
    color: colors.primary,
  },
  syncBannerSubtitle: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
    marginTop: 1,
  },
  syncNowBtn: {
    backgroundColor: colors.primary,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: borderRadius.sm,
  },
  syncNowBtnText: {
    ...typography.labelCaps,
    fontSize: 11,
    fontWeight: '700',
    color: colors.onPrimary,
  },

  // ─── Search & Filters ───────────────────────────────────────────────────────
  searchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.xl,
    paddingHorizontal: 12,
    paddingVertical: Platform.OS === 'ios' ? 10 : 6,
    gap: 8,
  },
  searchInput: {
    flex: 1,
    ...typography.bodyMd,
    fontSize: 13,
    color: colors.onSurface,
    padding: 0,
  },
  filterChipScroll: {
    gap: 8,
    paddingVertical: 2,
  },
  filterChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: borderRadius.round,
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  filterChipSelected: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  filterChipText: {
    ...typography.caption,
    fontSize: 12,
    fontWeight: '500',
    color: colors.onSurfaceVariant,
  },
  filterChipTextSelected: {
    color: colors.onPrimary,
    fontWeight: '700',
  },

  // ─── Count & Add Row ───────────────────────────────────────────────────────
  countRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  countText: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
    fontWeight: '500',
  },
  newInspectionSmallBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.primary,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: borderRadius.sm,
  },
  newInspectionSmallBtnText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.onPrimary,
  },

  // ─── Inspection Cards ──────────────────────────────────────────────────────
  cardContainer: {
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    overflow: 'hidden',
  },
  inspectionRow: {
    padding: 14,
    gap: 6,
  },
  rowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  rowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  rowInspNumber: {
    ...typography.labelCaps,
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
  rowDate: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
  rowProductName: {
    ...typography.bodyMd,
    fontSize: 14,
    fontWeight: '600',
    color: colors.onSurface,
  },
  rowMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    flexWrap: 'wrap',
  },
  rowBrand: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
  rowLocationBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
  },
  rowLocation: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
  rowBottomActions: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 4,
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: colors.surfaceContainerHigh,
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: borderRadius.round,
    borderWidth: 1,
  },
  statusBadgeText: {
    ...typography.caption,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.2,
  },
  reportBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: borderRadius.sm,
    backgroundColor: 'rgba(2, 132, 199, 0.08)',
  },
  reportBadgeText: {
    ...typography.caption,
    fontSize: 10,
    fontWeight: '600',
    color: colors.primary,
  },
  warningBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: borderRadius.sm,
    backgroundColor: colors.statusAmberBg,
  },
  warningBadgeText: {
    ...typography.caption,
    fontSize: 10,
    fontWeight: '600',
    color: colors.statusAmberText,
  },
  viewArrowRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
  },
  viewArrowText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.primary,
  },

  // ─── Offline Workflow Styles ───────────────────────────────────────────────
  offlineWorkflowContainer: {
    gap: 14,
  },
  offlineBanner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: colors.statusAmberBg,
    borderColor: 'rgba(230, 81, 0, 0.25)',
    borderWidth: 1,
    borderRadius: borderRadius.xl,
    padding: 14,
    gap: 12,
  },
  offlineBannerTitle: {
    ...typography.bodyMd,
    fontSize: 14,
    fontWeight: '700',
    color: colors.statusAmberText,
  },
  offlineBannerSubtitle: {
    ...typography.caption,
    fontSize: 12,
    lineHeight: 16,
    color: colors.onSurface,
    marginTop: 2,
  },
  offlineActionsRow: {
    flexDirection: 'row',
    gap: 10,
  },
  retryBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.primary,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: borderRadius.xl,
    gap: 6,
  },
  retryBtnText: {
    ...typography.labelCaps,
    fontSize: 13,
    color: colors.onPrimary,
  },
  captureOfflineBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceContainerLowest,
    borderColor: colors.primary,
    borderWidth: 1,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: borderRadius.xl,
    gap: 6,
  },
  captureOfflineBtnText: {
    ...typography.labelCaps,
    fontSize: 13,
    color: colors.primary,
  },
  sectionHeaderRow: {
    marginTop: 6,
  },
  sectionTitle: {
    ...typography.sectionHeader,
    fontSize: 14,
    fontWeight: '700',
    color: colors.onSurface,
  },
  emptyDraftsCard: {
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: borderRadius.xl,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    padding: 24,
    gap: 6,
  },
  emptyDraftsTitle: {
    ...typography.bodyMd,
    fontSize: 14,
    fontWeight: '700',
    color: colors.onSurface,
  },
  emptyDraftsSubtitle: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
  },
  draftCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: borderRadius.xl,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    padding: 14,
    gap: 10,
  },
  draftCardTop: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 8,
  },
  draftIdText: {
    ...typography.labelCaps,
    fontSize: 12,
    color: colors.primary,
    fontWeight: '700',
  },
  draftProductText: {
    ...typography.bodyMd,
    fontSize: 14,
    fontWeight: '600',
    color: colors.onSurface,
    marginTop: 2,
  },
  draftDateText: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
    marginTop: 2,
  },
  draftBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: borderRadius.round,
    borderWidth: 1,
  },
  draftBadgePending: {
    backgroundColor: colors.statusAmberBg,
    borderColor: 'rgba(230, 81, 0, 0.25)',
  },
  draftBadgeSynced: {
    backgroundColor: colors.statusGreenBg,
    borderColor: 'rgba(27, 94, 32, 0.25)',
  },
  draftBadgeText: {
    ...typography.caption,
    fontSize: 10,
    fontWeight: '700',
  },
  draftCardBottom: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: colors.surfaceContainerHigh,
  },
  draftImagesCount: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  draftImagesText: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
  continueCaptureBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
  },
  continueCaptureBtnText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '700',
    color: colors.primary,
  },

  // ─── Empty State ───────────────────────────────────────────────────────────
  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    padding: 36,
    gap: 8,
  },
  emptyTitle: {
    ...typography.bodyMd,
    fontSize: 15,
    fontWeight: '700',
    color: colors.onSurface,
  },
  emptySubtitle: {
    ...typography.bodySm,
    fontSize: 12,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
    maxWidth: 280,
  },
});
