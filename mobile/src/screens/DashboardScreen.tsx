import React, { useState, useCallback } from 'react';
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
import { SafeAreaView } from 'react-native-safe-area-context';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { BottomNav, BOTTOM_NAV_TAB_HEIGHT } from '../components/BottomNav';
import { ProfileAvatar } from '../components/ProfileAvatar';
import { api } from '../services/api';
import { authStorage } from '../services/authStorage';
import { getTimeBasedGreeting } from '../services/dateUtils';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

// Tab Section Modes
type DashboardTab = 'registry' | 'pending';

// Filter Chip Definitions
interface FilterChip {
  id: string;
  label: string;
  matcher?: (item: any) => boolean;
}

const FILTER_CHIPS: FilterChip[] = [
  { id: 'all', label: 'All' },
  { id: 'processing', label: 'Processing', matcher: (i) => ['IMAGES_UPLOADED', 'OCR_PROCESSING', 'EXTRACTION_COMPLETE', 'PROCESSING'].includes((i.status || '').toUpperCase()) },
  { id: 'pending_verification', label: 'Needs Verification', matcher: (i) => (i.overall_status || '').toUpperCase() === 'NEEDS_MANUAL_VERIFICATION' },
  { id: 'potential_non_compliance', label: 'Potential Non-Compliance', matcher: (i) => ['POTENTIAL_NON_COMPLIANCE', 'FAIL', 'CONFIRMED'].includes((i.overall_status || '').toUpperCase()) },
  { id: 'compliant', label: 'Compliant', matcher: (i) => ['NO_POTENTIAL_VIOLATIONS', 'VERIFIED_COMPLIANT', 'PASS'].includes((i.overall_status || '').toUpperCase()) },
  { id: 'completed', label: 'Completed', matcher: (i) => ['COMPLETED', 'FINALIZED'].includes((i.status || '').toUpperCase()) },
  { id: 'report_generated', label: 'Report Generated', matcher: (i) => Boolean(i.has_report) },
];

export const DashboardScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const insets = useSafeAreaInsets();
  const [profile, setProfile] = useState<any>(null);
  const [kpis, setKpis] = useState<any>(null);
  const [kpiError, setKpiError] = useState(false);
  const [inspections, setInspections] = useState<any[]>([]);
  const [pendingActions, setPendingActions] = useState<any[]>([]);
  const [registryError, setRegistryError] = useState(false);
  const [pendingActionsError, setPendingActionsError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Active Tab & Filter State
  const [activeTab, setActiveTab] = useState<DashboardTab>('registry');
  const [selectedChipId, setSelectedChipId] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [currentDate, setCurrentDate] = useState(() => new Date());

  const loadData = async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      let kpiFailed = false;
      let registryFailed = false;
      let pendingFailed = false;

      const [prof, kpiRes, inspRes, pendingRes] = await Promise.all([
        authStorage.getProfile(),
        api.getDashboardSummary().catch((err) => {
          console.warn('[Dashboard] getDashboardSummary failed:', err);
          kpiFailed = true;
          return null;
        }),
        api.getDashboardInspections({ limit: 100 }).catch((err) => {
          console.warn('[Dashboard] getDashboardInspections failed:', err);
          registryFailed = true;
          return null;
        }),
        api.getDashboardPendingActions(50).catch((err) => {
          console.warn('[Dashboard] getDashboardPendingActions failed:', err);
          pendingFailed = true;
          return null;
        }),
      ]);

      setProfile(prof);
      setKpiError(kpiFailed || !kpiRes);
      setKpis(kpiRes);

      const isRegErr = registryFailed || inspRes === null;
      setRegistryError(isRegErr);
      if (inspRes && Array.isArray(inspRes.items)) {
        setInspections(inspRes.items);
      } else if (!registryFailed) {
        setInspections([]);
      }

      const isPendingErr = pendingFailed || pendingRes === null;
      setPendingActionsError(isPendingErr);
      if (pendingRes && Array.isArray(pendingRes.items)) {
        setPendingActions(pendingRes.items);
      } else if (!pendingFailed) {
        setPendingActions([]);
      }
    } catch (err) {
      if (!silent) {
        console.error('Failed to load inspector dashboard:', err);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useFocusEffect(
    useCallback(() => {
      setCurrentDate(new Date());
      loadData(false);
    }, [])
  );

  const onRefresh = () => {
    setRefreshing(true);
    setCurrentDate(new Date());
    loadData(false);
  };

  const todayStr = currentDate.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });

  const formatCount = (val?: number | null) => {
    if (val === undefined || val === null) {
      return '—';
    }
    return val < 10 ? `0${val}` : `${val}`;
  };

  // Filter Registry Items
  const filteredInspections = inspections.filter((item) => {
    // 1. Search Query Filter
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchNum = (item.inspection_number || '').toLowerCase().includes(q);
      const matchProd = (item.product_name || '').toLowerCase().includes(q);
      const matchBrand = (item.brand_name || '').toLowerCase().includes(q);
      const matchLoc = (item.location || '').toLowerCase().includes(q);
      if (!matchNum && !matchProd && !matchBrand && !matchLoc) return false;
    }

    // 2. Chip Filter
    if (selectedChipId && selectedChipId !== 'all') {
      const chip = FILTER_CHIPS.find((c) => c.id === selectedChipId);
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

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
      <View style={styles.container}>
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={[
            styles.scrollContent,
            { paddingBottom: BOTTOM_NAV_TAB_HEIGHT + Math.max(insets.bottom, 6) + 16 },
          ]}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
          showsVerticalScrollIndicator={false}
        >
          {/* Top Header */}
          <View style={styles.welcomeHeader}>
            <View style={styles.welcomeHeaderRow}>
              <View style={styles.welcomeHeaderTextCol}>
                <Text style={styles.welcomeGreeting}>
                  {`${getTimeBasedGreeting(currentDate)}, ${profile?.full_name || 'Officer'}`}
                </Text>
                <View style={styles.identityRow}>
                  <Text style={styles.welcomeSubtext} numberOfLines={1} ellipsizeMode="tail">
                    ID: {profile?.officer_id || 'ID Pending'} • {todayStr}
                  </Text>
                  <View style={[styles.roleBadge, styles.roleBadgeInspector]}>
                    <Text style={[styles.roleBadgeText, styles.roleBadgeTextInspector]}>
                      FIELD INSPECTOR
                    </Text>
                  </View>
                </View>
              </View>
              <TouchableOpacity
                onPress={() => navigation.navigate('Profile')}
                activeOpacity={0.7}
                accessibilityRole="button"
                accessibilityLabel="Navigate to Profile"
              >
                <ProfileAvatar size={36} />
              </TouchableOpacity>
            </View>
          </View>

          {loading ? (
            <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 40 }} />
          ) : (
            <>
              {kpiError && (
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: colors.statusAmberBg, paddingHorizontal: 12, paddingVertical: 8, borderRadius: borderRadius.sm, marginHorizontal: spacing.marginX, marginBottom: 12, borderWidth: 1, borderColor: 'rgba(230, 81, 0, 0.25)' }}>
                  <Text style={{ fontSize: 12, color: colors.statusAmberText, flex: 1 }}>Unable to load live dashboard statistics.</Text>
                  <TouchableOpacity onPress={() => loadData(false)} activeOpacity={0.7} style={{ paddingHorizontal: 8, paddingVertical: 4 }}>
                    <Text style={{ fontSize: 12, fontWeight: '700', color: colors.statusAmberText }}>Retry</Text>
                  </TouchableOpacity>
                </View>
              )}
              {/* Statutory KPI Grid (All 7 Metrics) */}
              <View style={styles.metricsContainer}>
                {/* Row 1: Core Lifecycle */}
                <View style={styles.metricsRow}>
                  <View style={styles.metricCard}>
                    <Text style={styles.metricLabelDefault}>Total Inspections</Text>
                    <Text style={styles.metricValuePrimary}>{formatCount(kpis?.total_inspections)}</Text>
                  </View>
                  <View style={styles.metricCard}>
                    <Text style={styles.metricLabelDefault}>Completed</Text>
                    <Text style={styles.metricValuePrimary}>{formatCount(kpis?.completed_inspections)}</Text>
                  </View>
                  <View style={styles.metricCard}>
                    <Text style={styles.metricLabelGreen}>Compliant</Text>
                    <Text style={styles.metricValueGreen}>{formatCount(kpis?.compliant_inspections)}</Text>
                  </View>
                </View>

                {/* Row 2: Enforcement & Compliance Risks */}
                <View style={styles.metricsRow}>
                  <View style={styles.metricCard}>
                    <Text style={styles.metricLabelRed}>Non-Compliance</Text>
                    <Text style={styles.metricValueRed}>{formatCount(kpis?.potential_non_compliance)}</Text>
                  </View>
                  <View style={styles.metricCard}>
                    <Text style={styles.metricLabelAmber}>Pending Verif.</Text>
                    <Text style={styles.metricValueAmber}>{formatCount(kpis?.pending_verification)}</Text>
                  </View>
                  <View style={styles.metricCard}>
                    <Text style={styles.metricLabelDefault}>Reports Gen.</Text>
                    <Text style={styles.metricValuePrimary}>{formatCount(kpis?.reports_generated)}</Text>
                  </View>
                </View>

                {/* Bottom Metric: Inspections Requiring Manual Action */}
                <TouchableOpacity
                  style={styles.manualActionBanner}
                  onPress={() => setActiveTab('pending')}
                  activeOpacity={0.7}
                  accessibilityRole="button"
                  accessibilityLabel="View Action Required items"
                >
                  <View style={styles.manualActionLeft}>
                    <MaterialIcons name="assignment-late" size={20} color={colors.statusAmberText} />
                    <Text style={styles.manualActionTitle}>Action Required (Declarations / Violations)</Text>
                  </View>
                  <View style={styles.manualActionRight}>
                    <View style={styles.manualActionBadge}>
                      <Text style={styles.manualActionCount}>{formatCount(kpis?.manual_verification_required)}</Text>
                    </View>
                    <MaterialIcons name="chevron-right" size={18} color={colors.statusAmberText} />
                  </View>
                </TouchableOpacity>
              </View>

              {/* Tab Navigation Switcher */}
              <View style={styles.tabBar}>
                <TouchableOpacity
                  style={[styles.tabButton, activeTab === 'registry' && styles.tabButtonActive]}
                  onPress={() => setActiveTab('registry')}
                >
                  <MaterialIcons
                    name="list-alt"
                    size={16}
                    color={activeTab === 'registry' ? colors.primary : colors.onSurfaceVariant}
                  />
                  <Text style={[styles.tabButtonText, activeTab === 'registry' && styles.tabButtonTextActive]}>
                    Registry {registryError ? '(!)' : `(${inspections.length})`}
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[styles.tabButton, activeTab === 'pending' && styles.tabButtonActive]}
                  onPress={() => setActiveTab('pending')}
                >
                  <MaterialIcons
                    name="pending-actions"
                    size={16}
                    color={activeTab === 'pending' ? colors.primary : colors.onSurfaceVariant}
                  />
                  <Text style={[styles.tabButtonText, activeTab === 'pending' && styles.tabButtonTextActive]}>
                    Actions {pendingActionsError ? '(!)' : `(${pendingActions.length})`}
                  </Text>
                </TouchableOpacity>
              </View>

              {/* TAB 1: INSPECTIONS REGISTRY */}
              {activeTab === 'registry' && (
                <View style={styles.sectionContainer}>
                  {/* Search Input */}
                  <View style={styles.searchBox}>
                    <MaterialIcons name="search" size={20} color={colors.onSurfaceVariant} />
                    <TextInput
                      style={styles.searchInput}
                      placeholder="Search by ID, Product, Brand, Location..."
                      placeholderTextColor={colors.onSurfaceVariant}
                      value={searchQuery}
                      onChangeText={setSearchQuery}
                      clearButtonMode="while-editing"
                    />
                    {searchQuery.length > 0 && (
                      <TouchableOpacity onPress={() => setSearchQuery('')}>
                        <MaterialIcons name="close" size={18} color={colors.onSurfaceVariant} />
                      </TouchableOpacity>
                    )}
                  </View>

                  {/* Filter Chips */}
                  <ScrollView
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    contentContainerStyle={styles.chipsScrollContent}
                    style={styles.chipsScroll}
                  >
                    {FILTER_CHIPS.map((chip) => {
                      const isSelected = selectedChipId === chip.id;
                      return (
                        <TouchableOpacity
                          key={chip.id}
                          style={[
                            styles.chipButton,
                            isSelected && styles.chipButtonActive,
                          ]}
                          onPress={() => setSelectedChipId(chip.id)}
                          activeOpacity={0.8}
                        >
                          <Text style={[styles.chipText, isSelected && styles.chipTextActive]}>
                            {chip.label}
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </ScrollView>

                  {/* Inspections List */}
                  <View style={styles.cardContainer}>
                    {registryError ? (
                      <View style={styles.emptyContainer}>
                        <MaterialIcons name="error-outline" size={36} color={colors.statusRedText} />
                        <Text style={[styles.emptyTitle, { color: colors.statusRedText }]}>
                          Unable to load inspections.
                        </Text>
                        <Text style={styles.emptySubtitle}>
                          A network or server error occurred while retrieving the registry.
                        </Text>
                        <TouchableOpacity
                          style={styles.retryButton}
                          onPress={() => loadData(false)}
                          activeOpacity={0.7}
                        >
                          <MaterialIcons name="refresh" size={16} color="#FFFFFF" />
                          <Text style={styles.retryButtonText}>Retry</Text>
                        </TouchableOpacity>
                      </View>
                    ) : filteredInspections.length === 0 ? (
                      <View style={styles.emptyContainer}>
                        <MaterialIcons
                          name={inspections.length === 0 ? 'inventory-2' : 'search-off'}
                          size={36}
                          color={colors.outline}
                        />
                        <Text style={styles.emptyTitle}>
                          {inspections.length === 0
                            ? 'No inspections recorded yet.'
                            : 'No matching inspections found.'}
                        </Text>
                        <Text style={styles.emptySubtitle}>
                          {inspections.length === 0
                            ? 'Start a new inspection using the + button below.'
                            : 'Adjust your search or filter chips.'}
                        </Text>
                      </View>
                    ) : (
                      filteredInspections.map((item, idx) => {
                        const isLast = idx === filteredInspections.length - 1;
                        const badge = getStatusBadgeProps(item.overall_status || item.status);
                        const dateStr = item.created_at
                          ? new Date(item.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
                          : 'Not Available';
                        const productName = item.product_name || 'Not Available';
                        const brandName = item.brand_name ? ` • ${item.brand_name}` : '';
                        const categoryStr = item.category || 'Not Available';
                        const locationStr = item.location || 'Not Available';

                        return (
                          <TouchableOpacity
                            key={item.id || idx}
                            style={[styles.inspectionRow, !isLast && styles.rowBorder]}
                            onPress={() => handleInspectionPress(item)}
                            activeOpacity={0.7}
                            accessibilityRole="button"
                            accessibilityLabel={`Inspection ${item.inspection_number || 'ID'}, ${productName}`}
                          >
                            <View style={styles.rowTopHeader}>
                              <Text style={styles.rowIdText}>{item.inspection_number || 'Not Available'}</Text>
                              <Text style={styles.rowDateText}>{dateStr}</Text>
                            </View>

                            <Text style={styles.rowProductText} numberOfLines={1}>
                              {productName}{brandName}
                            </Text>

                            <View style={styles.rowMetaRow}>
                              <Text style={styles.rowMetaText} numberOfLines={1}>
                                {categoryStr} • {locationStr}
                              </Text>
                              {item.inspector_name ? (
                                <Text style={styles.rowInspectorText}>Off: {item.inspector_name}</Text>
                              ) : null}
                            </View>

                            <View style={styles.badgeRow}>
                              <View style={[styles.statusBadge, { backgroundColor: badge.bg, borderColor: badge.border }]}>
                                <Text style={[styles.statusBadgeText, { color: badge.text }]}>{badge.label}</Text>
                              </View>

                              {item.has_report && (
                                <View style={styles.reportBadge}>
                                  <MaterialIcons name="description" size={12} color={colors.primary} />
                                  <Text style={styles.reportBadgeText}>PDF Report</Text>
                                </View>
                              )}

                              {item.pending_actions_count > 0 && (
                                <View style={styles.warningBadge}>
                                  <MaterialIcons name="priority-high" size={12} color={colors.statusAmberText} />
                                  <Text style={styles.warningBadgeText}>{item.pending_actions_count} Action(s)</Text>
                                </View>
                              )}
                            </View>
                          </TouchableOpacity>
                        );
                      })
                    )}
                  </View>
                </View>
              )}

              {/* TAB 2: PENDING ACTIONS QUEUE */}
              {activeTab === 'pending' && (
                <View style={styles.sectionContainer}>
                  <Text style={styles.sectionHeaderTitle}>Actionable Inspection Tasks</Text>
                  <Text style={styles.sectionHeaderSubtitle}>
                    Items requiring statutory verification, violation adjudication, or image recapture.
                  </Text>

                  <View style={styles.cardContainer}>
                    {pendingActionsError ? (
                      <View style={styles.emptyContainer}>
                        <MaterialIcons name="error-outline" size={36} color={colors.statusRedText} />
                        <Text style={[styles.emptyTitle, { color: colors.statusRedText }]}>
                          Unable to load pending actions.
                        </Text>
                        <Text style={styles.emptySubtitle}>
                          A network or server error occurred while retrieving actions.
                        </Text>
                        <TouchableOpacity
                          style={styles.retryButton}
                          onPress={() => loadData(false)}
                          activeOpacity={0.7}
                        >
                          <MaterialIcons name="refresh" size={16} color="#FFFFFF" />
                          <Text style={styles.retryButtonText}>Retry</Text>
                        </TouchableOpacity>
                      </View>
                    ) : pendingActions.length === 0 ? (
                      <View style={styles.emptyContainer}>
                        <MaterialIcons name="check-circle" size={40} color={colors.statusGreenText} />
                        <Text style={styles.emptyTitle}>All inspections verified!</Text>
                        <Text style={styles.emptySubtitle}>No pending adjudication or unresolved extractions.</Text>
                      </View>
                    ) : (
                      pendingActions.map((action, idx) => {
                        const isLast = idx === pendingActions.length - 1;
                        const isCritical = action.severity === 'CRITICAL';

                        return (
                          <TouchableOpacity
                            key={idx}
                            style={[styles.actionRow, !isLast && styles.rowBorder]}
                            onPress={() => {
                              navigation.navigate('Findings', {
                                inspectionId: action.inspection_id,
                                inspectionNumber: action.inspection_number,
                              });
                            }}
                            activeOpacity={0.7}
                          >
                            <View style={styles.actionHeader}>
                              <View style={[styles.severityBadge, isCritical ? styles.severityCritical : styles.severityWarning]}>
                                <Text style={[styles.severityText, isCritical ? styles.textRed : styles.textAmber]}>
                                  {action.severity}
                                </Text>
                              </View>
                              <Text style={styles.actionInspNumber}>{action.inspection_number}</Text>
                            </View>

                            <Text style={styles.actionTitle}>{action.title}</Text>
                            <Text style={styles.actionDescription}>{action.description}</Text>
                            <Text style={styles.actionProduct}>{action.product_name}</Text>

                            <View style={styles.actionReviewBtn}>
                              <Text style={styles.actionReviewText}>Adjudicate & Review</Text>
                              <MaterialIcons name="arrow-forward" size={14} color={colors.primary} />
                            </View>
                          </TouchableOpacity>
                        );
                      })
                    )}
                  </View>
                </View>
              )}


            </>
          )}
        </ScrollView>

        {/* Bottom Navigation Bar */}
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
    position: 'relative',
  },
  scrollContent: {
    paddingHorizontal: spacing.marginX,
    paddingTop: spacing.stackMd,
    paddingBottom: 8,
  },
  welcomeHeader: {
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    paddingBottom: spacing.stackSm,
    marginBottom: spacing.stackSm,
  },
  welcomeHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  welcomeHeaderTextCol: {
    flex: 1,
    paddingRight: spacing.stackSm,
  },
  welcomeGreeting: {
    ...typography.headlineLg,
    fontSize: 20,
    lineHeight: 28,
    color: colors.primary,
  },
  identityRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'nowrap',
    gap: 8,
    marginTop: 4,
  },
  welcomeSubtext: {
    ...typography.bodySm,
    fontSize: 12.5,
    lineHeight: 18,
    color: colors.onSurfaceVariant,
    flexShrink: 1,
  },
  metricsContainer: {
    gap: spacing.tight,
    marginBottom: spacing.stackMd,
  },
  metricsRow: {
    flexDirection: 'row',
    gap: spacing.tight,
  },
  metricCard: {
    flex: 1,
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.stackSm,
    alignItems: 'center',
  },
  metricLabelDefault: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.onSurfaceVariant,
    textAlign: 'center',
  },
  metricLabelGreen: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.statusGreenText,
    textAlign: 'center',
  },
  metricLabelAmber: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.statusAmberText,
    textAlign: 'center',
  },
  metricLabelRed: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.statusRedText,
    textAlign: 'center',
  },
  metricValuePrimary: {
    ...typography.headlineLg,
    fontSize: 18,
    lineHeight: 24,
    color: colors.primary,
    marginTop: 2,
    fontWeight: '700',
  },
  metricValueGreen: {
    ...typography.headlineLg,
    fontSize: 18,
    lineHeight: 24,
    color: colors.statusGreenText,
    marginTop: 2,
    fontWeight: '700',
  },
  metricValueAmber: {
    ...typography.headlineLg,
    fontSize: 18,
    lineHeight: 24,
    color: colors.statusAmberText,
    marginTop: 2,
    fontWeight: '700',
  },
  metricValueRed: {
    ...typography.headlineLg,
    fontSize: 18,
    lineHeight: 24,
    color: colors.statusRedText,
    marginTop: 2,
    fontWeight: '700',
  },
  manualActionBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.statusAmberBg,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: 'rgba(230, 81, 0, 0.25)',
    paddingHorizontal: spacing.stackSm,
    paddingVertical: spacing.tight,
  },
  manualActionLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  manualActionTitle: {
    ...typography.caption,
    fontSize: 12,
    fontWeight: '700',
    color: colors.statusAmberText,
  },
  manualActionRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  manualActionBadge: {
    backgroundColor: colors.surfaceContainerLowest,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: borderRadius.round,
    borderWidth: 1,
    borderColor: colors.statusAmberText,
  },
  manualActionCount: {
    ...typography.caption,
    fontWeight: '700',
    fontSize: 12,
    color: colors.statusAmberText,
  },
  tabBar: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceContainerLow,
    borderRadius: borderRadius.lg,
    padding: 2,
    marginBottom: spacing.stackMd,
  },
  tabButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingVertical: 8,
    borderRadius: borderRadius.DEFAULT,
  },
  tabButtonActive: {
    backgroundColor: colors.surfaceContainerLowest,
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  tabButtonText: {
    ...typography.caption,
    fontSize: 11.5,
    fontWeight: '600',
    color: colors.onSurfaceVariant,
  },
  tabButtonTextActive: {
    color: colors.primary,
    fontWeight: '700',
  },
  sectionContainer: {
    gap: spacing.stackSm,
  },
  sectionHeaderTitle: {
    ...typography.sectionHeader,
    fontSize: 15,
    color: colors.primary,
    fontWeight: '700',
  },
  sectionHeaderSubtitle: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
    marginBottom: 4,
  },
  searchBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    paddingHorizontal: 12,
    height: 40,
    gap: 8,
  },
  searchInput: {
    flex: 1,
    ...typography.bodySm,
    color: colors.onSurface,
  },
  chipsScroll: {
    marginBottom: 4,
  },
  chipsScrollContent: {
    gap: 6,
    paddingBottom: 2,
  },
  chipButton: {
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: borderRadius.round,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    backgroundColor: colors.surfaceContainerLowest,
  },
  chipButtonActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  chipText: {
    ...typography.caption,
    fontSize: 11.5,
    fontWeight: '600',
    color: colors.onSurfaceVariant,
  },
  chipTextActive: {
    color: '#ffffff',
  },
  cardContainer: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    overflow: 'hidden',
  },
  inspectionRow: {
    padding: spacing.stackSm,
    gap: 4,
  },
  rowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  rowTopHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  rowIdText: {
    ...typography.bodySm,
    fontSize: 12.5,
    fontWeight: '700',
    color: colors.primary,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  },
  rowDateText: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
  rowProductText: {
    ...typography.bodyMd,
    fontSize: 14,
    fontWeight: '600',
    color: colors.onSurface,
  },
  rowMetaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  rowMetaText: {
    ...typography.caption,
    fontSize: 11.5,
    color: colors.onSurfaceVariant,
  },
  rowInspectorText: {
    ...typography.caption,
    fontSize: 11,
    color: colors.primary,
    fontStyle: 'italic',
  },
  badgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 2,
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
  },
  statusBadgeText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
  },
  reportBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  reportBadgeText: {
    ...typography.caption,
    fontSize: 11,
    color: colors.primary,
    fontWeight: '600',
  },
  warningBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    backgroundColor: colors.statusAmberBg,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    borderColor: 'rgba(230, 81, 0, 0.25)',
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  warningBadgeText: {
    ...typography.caption,
    fontSize: 11,
    color: colors.statusAmberText,
    fontWeight: '700',
  },
  roleBadge: {
    borderRadius: borderRadius.full,
    paddingHorizontal: 7,
    paddingVertical: 1,
    alignSelf: 'center',
    flexShrink: 0,
  },
  roleBadgeInspector: {
    backgroundColor: '#E8F0FE',
    borderWidth: 1,
    borderColor: '#AECBFA',
  },
  roleBadgeSupervisor: {
    backgroundColor: '#F3E8FD',
    borderWidth: 1,
    borderColor: '#D7AEFB',
  },
  roleBadgeAdmin: {
    backgroundColor: '#E6F4EA',
    borderWidth: 1,
    borderColor: '#A8DAB5',
  },
  roleBadgeText: {
    fontSize: 9.5,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  roleBadgeTextInspector: {
    color: '#1967D2',
  },
  roleBadgeTextSupervisor: {
    color: '#8430CE',
  },
  roleBadgeTextAdmin: {
    color: '#137333',
  },
  emptyContainer: {
    paddingVertical: 32,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  emptyTitle: {
    ...typography.bodyMd,
    fontWeight: '600',
    color: colors.onSurface,
  },
  emptySubtitle: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
    paddingHorizontal: 20,
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: colors.primary,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: borderRadius.md,
    marginTop: 8,
  },
  retryButtonText: {
    ...typography.caption,
    fontSize: 13,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  // Pending Action Row Styles
  actionRow: {
    padding: spacing.stackSm,
    gap: 4,
  },
  actionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  severityBadge: {
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
  },
  severityCritical: {
    backgroundColor: colors.statusRedBg,
    borderColor: 'rgba(183, 28, 28, 0.25)',
  },
  severityWarning: {
    backgroundColor: colors.statusAmberBg,
    borderColor: 'rgba(230, 81, 0, 0.25)',
  },
  severityText: {
    ...typography.caption,
    fontSize: 10,
    fontWeight: '700',
  },
  textRed: {
    color: colors.statusRedText,
  },
  textAmber: {
    color: colors.statusAmberText,
  },
  actionInspNumber: {
    ...typography.caption,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
    color: colors.onSurfaceVariant,
  },
  actionTitle: {
    ...typography.bodyMd,
    fontSize: 13.5,
    fontWeight: '700',
    color: colors.primary,
  },
  actionDescription: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurface,
    lineHeight: 16,
  },
  actionProduct: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
    fontStyle: 'italic',
  },
  actionReviewBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    alignSelf: 'flex-start',
    marginTop: 4,
    backgroundColor: colors.surfaceContainerLow,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  actionReviewText: {
    ...typography.caption,
    fontSize: 11.5,
    fontWeight: '700',
    color: colors.primary,
  },
  // Analytics Styles
  analyticsRatesRow: {
    flexDirection: 'row',
    gap: spacing.tight,
  },
  rateCard: {
    flex: 1,
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderTopWidth: 3,
    padding: spacing.stackSm,
    alignItems: 'center',
  },
  rateLabel: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
    fontWeight: '600',
  },
  rateValue: {
    ...typography.headlineLg,
    fontSize: 18,
    fontWeight: '700',
    marginTop: 4,
  },
  breakdownCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    padding: spacing.stackSm,
    gap: 6,
  },
  cardHeaderTitle: {
    ...typography.bodySm,
    fontWeight: '700',
    color: colors.primary,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    paddingBottom: 4,
  },
  breakdownRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 2,
  },
  breakdownLabel: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurface,
    fontWeight: '500',
  },
  breakdownValueBadge: {
    backgroundColor: colors.surfaceContainerLow,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  breakdownValueText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '700',
    color: colors.onSurface,
  },
  breakdownCountText: {
    ...typography.caption,
    fontSize: 11.5,
    color: colors.onSurfaceVariant,
    fontWeight: '600',
  },
  subtleEmptyText: {
    ...typography.caption,
    color: colors.onSurfaceVariant,
    fontStyle: 'italic',
    paddingVertical: 4,
  },
});
