import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { BottomNav, BOTTOM_NAV_TAB_HEIGHT } from '../components/BottomNav';
import { api } from '../services/api';
import { useNavigation, useRoute } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const SupervisorAllInspectionsScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<any>();
  const insets = useSafeAreaInsets();

  const initialInspectorFilter = route.params?.inspectorIdFilter || '';

  // Filter States
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedStatus, setSelectedStatus] = useState('ALL');
  const [selectedCompliance, setSelectedCompliance] = useState('ALL');
  const [selectedInspectorId, setSelectedInspectorId] = useState(initialInspectorFilter);
  const [sortBy, setSortBy] = useState('created_at');
  const [sortOrder, setSortOrder] = useState('desc');

  // Pagination & Data States
  const [page, setPage] = useState(1);
  const [pageSize] = useState(15);
  const [inspections, setInspections] = useState<any[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Inspector List for Filter
  const [inspectors, setInspectors] = useState<any[]>([]);

  // Load Inspectors once for filter
  useEffect(() => {
    api.getSupervisorInspectors()
      .then((res: any) => {
        if (res && res.inspectors) {
          setInspectors(res.inspectors);
        }
      })
      .catch(() => {});
  }, []);

  const fetchInspections = useCallback(async (targetPage = page, isRefresh = false) => {
    try {
      if (!isRefresh) setLoading(true);
      setError(null);

      const params: any = {
        page: targetPage,
        page_size: pageSize,
        sort_by: sortBy,
        sort_order: sortOrder,
      };

      if (searchQuery.trim()) params.search = searchQuery.trim();
      if (selectedStatus !== 'ALL') params.status = selectedStatus;
      if (selectedCompliance !== 'ALL') params.overall_status = selectedCompliance;
      if (selectedInspectorId.trim()) params.inspector_id = selectedInspectorId.trim();

      const res: any = await api.getSupervisorInspections(params);
      setInspections(res.items || []);
      setTotalCount(res.total_count || 0);
      setTotalPages(res.total_pages || 1);
      setPage(res.page || targetPage);
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch inspections from server.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [page, pageSize, searchQuery, selectedStatus, selectedCompliance, selectedInspectorId, sortBy, sortOrder]);

  useEffect(() => {
    fetchInspections(1);
  }, [selectedStatus, selectedCompliance, selectedInspectorId, sortBy, sortOrder]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchInspections(page, true);
  };

  const handleSearchSubmit = () => {
    fetchInspections(1);
  };

  const statusChips = [
    { label: 'All Status', value: 'ALL' },
    { label: 'Completed', value: 'COMPLETED' },
    { label: 'Rule Evaluated', value: 'RULE_EVALUATION_COMPLETE' },
    { label: 'Analyzing', value: 'ANALYZING' },
    { label: 'Draft', value: 'DRAFT' },
  ];

  const complianceChips = [
    { label: 'All Compliance', value: 'ALL' },
    { label: 'Compliant', value: 'NO_POTENTIAL_VIOLATIONS' },
    { label: 'Non-Compliant', value: 'POTENTIAL_NON_COMPLIANCE' },
    { label: 'Needs Verification', value: 'NEEDS_MANUAL_VERIFICATION' },
  ];

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
      <View style={styles.container}>
        {/* Top Header */}
        <View style={styles.topHeader}>
          <TouchableOpacity
            style={styles.backButton}
            onPress={() => navigation.navigate('SupervisorDashboard')}
          >
            <MaterialIcons name="arrow-back" size={24} color={colors.onSurface} />
          </TouchableOpacity>
          <View style={styles.headerTitleContainer}>
            <Text style={styles.headerTitle}>All Inspections</Text>
            <Text style={styles.headerSub}>{totalCount} Total Recorded</Text>
          </View>
          <TouchableOpacity
            style={styles.refreshIcon}
            onPress={() => fetchInspections(page)}
          >
            <MaterialIcons name="refresh" size={22} color={colors.primary} />
          </TouchableOpacity>
        </View>

        {/* Search Input */}
        <View style={styles.searchBarContainer}>
          <MaterialIcons name="search" size={20} color={colors.onSurfaceVariant} style={styles.searchIcon} />
          <TextInput
            style={styles.searchInput}
            placeholder="Search by ID, Product, Brand, Inspector..."
            placeholderTextColor={colors.outline}
            value={searchQuery}
            onChangeText={setSearchQuery}
            onSubmitEditing={handleSearchSubmit}
            returnKeyType="search"
          />
          {searchQuery.length > 0 && (
            <TouchableOpacity onPress={() => { setSearchQuery(''); fetchInspections(1); }}>
              <MaterialIcons name="close" size={18} color={colors.onSurfaceVariant} />
            </TouchableOpacity>
          )}
        </View>

        {/* Horizontal Filters */}
        <View style={styles.filtersSection}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipsScroll}>
            {/* Status Chips */}
            {statusChips.map((c) => (
              <TouchableOpacity
                key={c.value}
                style={[styles.filterChip, selectedStatus === c.value && styles.filterChipActive]}
                onPress={() => setSelectedStatus(c.value)}
              >
                <Text style={[styles.filterChipText, selectedStatus === c.value && styles.filterChipTextActive]}>
                  {c.label}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={[styles.chipsScroll, { marginTop: 6 }]}>
            {/* Compliance Chips */}
            {complianceChips.map((c) => (
              <TouchableOpacity
                key={c.value}
                style={[styles.filterChip, selectedCompliance === c.value && styles.filterChipActive]}
                onPress={() => setSelectedCompliance(c.value)}
              >
                <Text style={[styles.filterChipText, selectedCompliance === c.value && styles.filterChipTextActive]}>
                  {c.label}
                </Text>
              </TouchableOpacity>
            ))}
            {selectedInspectorId ? (
              <TouchableOpacity
                style={[styles.filterChip, styles.filterChipActive]}
                onPress={() => setSelectedInspectorId('')}
              >
                <Text style={styles.filterChipTextActive}>Officer: {selectedInspectorId} ✕</Text>
              </TouchableOpacity>
            ) : null}
          </ScrollView>
        </View>

        {/* List Content */}
        {loading && !refreshing ? (
          <View style={styles.centerContainer}>
            <ActivityIndicator size="large" color={colors.primary} />
            <Text style={styles.loadingText}>Fetching inspections from Neon DB...</Text>
          </View>
        ) : error ? (
          <View style={styles.centerContainer}>
            <MaterialIcons name="error-outline" size={44} color={colors.error} />
            <Text style={styles.errorTitle}>Failed to Load Inspections</Text>
            <Text style={styles.errorMessage}>{error}</Text>
            <TouchableOpacity style={styles.retryBtn} onPress={() => fetchInspections(page)}>
              <Text style={styles.retryBtnText}>Retry</Text>
            </TouchableOpacity>
          </View>
        ) : inspections.length === 0 ? (
          <View style={styles.centerContainer}>
            <MaterialIcons name="search-off" size={48} color={colors.outline} />
            <Text style={styles.emptyTitle}>No Matching Inspections</Text>
            <Text style={styles.emptySub}>Try adjusting your search query or filters.</Text>
          </View>
        ) : (
          <ScrollView
            style={styles.listArea}
            contentContainerStyle={[
              styles.listContent,
              { paddingBottom: insets.bottom + BOTTOM_NAV_TAB_HEIGHT + 30 },
            ]}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={[colors.primary]} />}
          >
            {inspections.map((item) => (
              <TouchableOpacity
                key={item.id}
                style={styles.card}
                activeOpacity={0.7}
                onPress={() =>
                  navigation.navigate('SupervisorInspectionDetail', {
                    inspectionId: item.id,
                    inspectionNumber: item.inspection_number,
                  })
                }
              >
                <View style={styles.cardTop}>
                  <View style={styles.cardNumRow}>
                    <Text style={styles.inspNumber}>{item.inspection_number}</Text>
                    {item.has_report && (
                      <View style={styles.reportTag}>
                        <MaterialIcons name="picture-as-pdf" size={12} color="#FFFFFF" />
                        <Text style={styles.reportTagText}>REPORT</Text>
                      </View>
                    )}
                  </View>
                  <View
                    style={[
                      styles.statusPill,
                      item.overall_status === 'POTENTIAL_NON_COMPLIANCE'
                        ? styles.statusPillRed
                        : item.overall_status === 'NO_POTENTIAL_VIOLATIONS'
                        ? styles.statusPillGreen
                        : styles.statusPillAmber,
                    ]}
                  >
                    <Text
                      style={[
                        styles.statusPillText,
                        item.overall_status === 'POTENTIAL_NON_COMPLIANCE'
                          ? styles.statusTextRed
                          : item.overall_status === 'NO_POTENTIAL_VIOLATIONS'
                          ? styles.statusTextGreen
                          : styles.statusTextAmber,
                      ]}
                    >
                      {item.overall_status || item.status}
                    </Text>
                  </View>
                </View>

                <Text style={styles.prodName}>{item.product_name}</Text>
                {item.brand_name ? <Text style={styles.brandName}>Brand: {item.brand_name}</Text> : null}

                <View style={styles.divider} />

                <View style={styles.metaRow}>
                  <View style={styles.metaCol}>
                    <Text style={styles.metaLabel}>Inspector</Text>
                    <Text style={styles.metaVal}>{item.inspector_name} ({item.inspector_id})</Text>
                  </View>
                  <View style={styles.metaCol}>
                    <Text style={styles.metaLabel}>Location</Text>
                    <Text style={styles.metaVal}>{item.location}</Text>
                  </View>
                </View>

                <View style={[styles.metaRow, { marginTop: 6 }]}>
                  <View style={styles.metaCol}>
                    <Text style={styles.metaLabel}>Category</Text>
                    <Text style={styles.metaVal}>{item.category}</Text>
                  </View>
                  <View style={styles.metaCol}>
                    <Text style={styles.metaLabel}>Date</Text>
                    <Text style={styles.metaVal}>
                      {new Date(item.created_at).toLocaleDateString('en-IN', {
                        day: 'numeric',
                        month: 'short',
                        year: 'numeric',
                      })}
                    </Text>
                  </View>
                </View>
              </TouchableOpacity>
            ))}

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <View style={styles.paginationRow}>
                <TouchableOpacity
                  style={[styles.pageBtn, page <= 1 && styles.pageBtnDisabled]}
                  disabled={page <= 1}
                  onPress={() => fetchInspections(page - 1)}
                >
                  <MaterialIcons name="chevron-left" size={20} color={page <= 1 ? colors.outline : colors.onSurface} />
                  <Text style={[styles.pageBtnText, page <= 1 && styles.pageBtnTextDisabled]}>Prev</Text>
                </TouchableOpacity>

                <Text style={styles.pageInfoText}>
                  Page {page} of {totalPages}
                </Text>

                <TouchableOpacity
                  style={[styles.pageBtn, page >= totalPages && styles.pageBtnDisabled]}
                  disabled={page >= totalPages}
                  onPress={() => fetchInspections(page + 1)}
                >
                  <Text style={[styles.pageBtnText, page >= totalPages && styles.pageBtnTextDisabled]}>Next</Text>
                  <MaterialIcons name="chevron-right" size={20} color={page >= totalPages ? colors.outline : colors.onSurface} />
                </TouchableOpacity>
              </View>
            )}
          </ScrollView>
        )}

        <BottomNav />
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.surface,
  },
  container: {
    flex: 1,
    backgroundColor: colors.surfaceContainerLowest,
  },
  topHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.outlineVariant,
  },
  backButton: {
    padding: 4,
    marginRight: spacing.sm,
  },
  headerTitleContainer: {
    flex: 1,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.onSurface,
  },
  headerSub: {
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
  refreshIcon: {
    padding: 4,
  },
  searchBarContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    marginHorizontal: spacing.md,
    marginTop: spacing.sm,
    paddingHorizontal: spacing.sm + 4,
    paddingVertical: spacing.xs + 2,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.outlineVariant,
  },
  searchIcon: {
    marginRight: 6,
  },
  searchInput: {
    flex: 1,
    fontSize: 13,
    color: colors.onSurface,
  },
  filtersSection: {
    paddingVertical: spacing.xs + 2,
    borderBottomWidth: 1,
    borderBottomColor: colors.outlineVariant,
    backgroundColor: colors.surface,
  },
  chipsScroll: {
    paddingHorizontal: spacing.md,
    gap: 6,
  },
  filterChip: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: borderRadius.full,
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.outlineVariant,
  },
  filterChipActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  filterChipText: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    fontWeight: '500',
  },
  filterChipTextActive: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
  listArea: {
    flex: 1,
  },
  listContent: {
    padding: spacing.md,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.xl,
  },
  loadingText: {
    marginTop: spacing.md,
    fontSize: 13,
    color: colors.onSurfaceVariant,
  },
  errorTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.onSurface,
    marginTop: spacing.sm,
  },
  errorMessage: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
    marginTop: 4,
    marginBottom: spacing.md,
  },
  retryBtn: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.xs + 4,
    borderRadius: borderRadius.md,
  },
  retryBtnText: {
    color: '#FFFFFF',
    fontWeight: '600',
    fontSize: 13,
  },
  emptyTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.onSurface,
    marginTop: spacing.sm,
  },
  emptySub: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    marginTop: 2,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    padding: spacing.md,
    marginBottom: spacing.sm + 4,
    borderWidth: 1,
    borderColor: colors.outlineVariant,
  },
  cardTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  cardNumRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  inspNumber: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.primary,
  },
  reportTag: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0D9488',
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: 4,
    gap: 3,
  },
  reportTagText: {
    color: '#FFFFFF',
    fontSize: 9,
    fontWeight: '700',
  },
  statusPill: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: borderRadius.full,
  },
  statusPillGreen: {
    backgroundColor: colors.statusGreenBg,
  },
  statusPillRed: {
    backgroundColor: colors.statusRedBg,
  },
  statusPillAmber: {
    backgroundColor: colors.statusAmberBg,
  },
  statusPillText: {
    fontSize: 10,
    fontWeight: '700',
  },
  statusTextGreen: {
    color: colors.statusGreenText,
  },
  statusTextRed: {
    color: colors.statusRedText,
  },
  statusTextAmber: {
    color: colors.statusAmberText,
  },
  prodName: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.onSurface,
  },
  brandName: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    marginTop: 1,
  },
  divider: {
    height: 1,
    backgroundColor: colors.outlineVariant,
    marginVertical: spacing.sm,
  },
  metaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  metaCol: {
    flex: 1,
  },
  metaLabel: {
    fontSize: 10,
    color: colors.onSurfaceVariant,
    fontWeight: '500',
    textTransform: 'uppercase',
  },
  metaVal: {
    fontSize: 12,
    color: colors.onSurface,
    fontWeight: '500',
    marginTop: 1,
  },
  paginationRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.md,
    paddingHorizontal: spacing.sm,
  },
  pageBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.outlineVariant,
    backgroundColor: colors.surface,
    gap: 2,
  },
  pageBtnDisabled: {
    opacity: 0.4,
  },
  pageBtnText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.onSurface,
  },
  pageBtnTextDisabled: {
    color: colors.outline,
  },
  pageInfoText: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    fontWeight: '500',
  },
});
