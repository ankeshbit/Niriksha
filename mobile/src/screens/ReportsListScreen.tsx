import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  TextInput,
  Alert,
  SafeAreaView,
  Platform,
  Modal,
  KeyboardAvoidingView,
} from 'react-native';
import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { BottomNav } from '../components/BottomNav';
import { ProfileAvatar } from '../components/ProfileAvatar';
import { api, getApiBaseUrl } from '../services/api';
import { authStorage } from '../services/authStorage';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export type ComplianceFilterType = 'ALL' | 'COMPLIANT' | 'NON_COMPLIANT' | 'MANUAL_REVIEW';
export type DateFilterType = 'ALL' | 'TODAY' | 'LAST_7_DAYS' | 'LAST_30_DAYS' | 'THIS_MONTH';
export type SortByType = 'NEWEST' | 'OLDEST' | 'ID_ASC' | 'PRODUCT_ASC';

export interface ReportItem {
  id: string;
  inspection_id: string;
  report_version?: number;
  pdf_path?: string;
  download_url?: string;
  legal_safety_statement?: string;
  generated_at?: string;
  created_at?: string;
  inspection_number?: string;
  product_name?: string;
  location?: string;
  overall_status?: string;
  status?: string;
}

export const ReportsListScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  // Active Applied Filters (Drives the derived list calculation)
  const [selectedCompliance, setSelectedCompliance] = useState<ComplianceFilterType>('ALL');
  const [selectedDateRange, setSelectedDateRange] = useState<DateFilterType>('ALL');
  const [selectedSortBy, setSelectedSortBy] = useState<SortByType>('NEWEST');

  // Filter Modal State (Temporary selections in the modal until Apply is tapped)
  const [filterModalVisible, setFilterModalVisible] = useState(false);
  const [tempCompliance, setTempCompliance] = useState<ComplianceFilterType>('ALL');
  const [tempDateRange, setTempDateRange] = useState<DateFilterType>('ALL');
  const [tempSortBy, setTempSortBy] = useState<SortByType>('NEWEST');

  const loadReports = async () => {
    try {
      const data = await api.getReportsList();
      const list: ReportItem[] = Array.isArray(data) ? data : data?.reports || data?.items || [];
      setReports(list);
    } catch (err) {
      console.error('Failed to load reports archive:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useFocusEffect(
    useCallback(() => {
      loadReports();
    }, [])
  );

  const onRefresh = () => {
    setRefreshing(true);
    loadReports();
  };

  // Open modal & copy currently applied filter state to temporary modal selections
  const handleOpenFilterModal = () => {
    setTempCompliance(selectedCompliance);
    setTempDateRange(selectedDateRange);
    setTempSortBy(selectedSortBy);
    setFilterModalVisible(true);
  };

  // Close modal without applying uncommitted temporary changes
  const handleCloseModal = () => {
    setFilterModalVisible(false);
  };

  // Commit temporary modal selections to applied state and close modal
  const handleApplyFilters = () => {
    setSelectedCompliance(tempCompliance);
    setSelectedDateRange(tempDateRange);
    setSelectedSortBy(tempSortBy);
    setFilterModalVisible(false);
  };

  // Reset temporary selections inside the modal to the required default state
  const handleResetModalFilters = () => {
    setTempCompliance('ALL');
    setTempDateRange('ALL');
    setTempSortBy('NEWEST');
  };

  // Reset all filters in both applied and modal state (used by empty state & quick actions)
  const handleResetAll = () => {
    setTempCompliance('ALL');
    setTempDateRange('ALL');
    setTempSortBy('NEWEST');
    setSelectedCompliance('ALL');
    setSelectedDateRange('ALL');
    setSelectedSortBy('NEWEST');
    setFilterModalVisible(false);
  };

  // Count active non-default filters
  const activeFilterCount =
    (selectedCompliance !== 'ALL' ? 1 : 0) +
    (selectedDateRange !== 'ALL' ? 1 : 0) +
    (selectedSortBy !== 'NEWEST' ? 1 : 0);

  // Derived filtered & sorted report list
  const filteredReports = useMemo(() => {
    return reports
      .filter((r) => {
        // 1. Text Search Filter (Inspection ID, Product Name, Location)
        if (searchQuery.trim()) {
          const q = searchQuery.trim().toLowerCase();
          const inspNum = String(r.inspection_number || '').toLowerCase();
          const prodName = String(r.product_name || '').toLowerCase();
          const loc = String(r.location || '').toLowerCase();
          const matchesSearch = inspNum.includes(q) || prodName.includes(q) || loc.includes(q);
          if (!matchesSearch) return false;
        }

        // 2. Compliance Status Filter
        if (selectedCompliance !== 'ALL') {
          const rawStatus = String(r.overall_status || r.status || '').trim().toUpperCase();

          const isCompliant =
            rawStatus === 'NO_POTENTIAL_VIOLATIONS' ||
            rawStatus === 'VERIFIED_COMPLIANT' ||
            rawStatus === 'COMPLIANT';

          const isNonCompliant =
            rawStatus === 'POTENTIAL_NON_COMPLIANCE' ||
            rawStatus === 'FAIL' ||
            rawStatus === 'NON_COMPLIANT';

          const isManualReview =
            rawStatus === 'NEEDS_MANUAL_VERIFICATION' ||
            rawStatus === 'INSUFFICIENT_EVIDENCE' ||
            rawStatus === 'MANUAL_REVIEW' ||
            rawStatus === 'NEEDS_REVIEW' ||
            (!isCompliant && !isNonCompliant);

          if (selectedCompliance === 'COMPLIANT' && !isCompliant) return false;
          if (selectedCompliance === 'NON_COMPLIANT' && !isNonCompliant) return false;
          if (selectedCompliance === 'MANUAL_REVIEW' && !isManualReview) return false;
        }

        // 3. Date Range Filter
        if (selectedDateRange !== 'ALL') {
          const dateStr = r.generated_at || r.created_at;
          if (!dateStr) return false;

          const reportDate = new Date(dateStr);
          if (isNaN(reportDate.getTime())) return false;

          const now = new Date();

          if (selectedDateRange === 'TODAY') {
            const isToday =
              reportDate.getFullYear() === now.getFullYear() &&
              reportDate.getMonth() === now.getMonth() &&
              reportDate.getDate() === now.getDate();
            if (!isToday) return false;
          } else if (selectedDateRange === 'LAST_7_DAYS') {
            const sevenDaysAgo = now.getTime() - 7 * 24 * 60 * 60 * 1000;
            if (reportDate.getTime() < sevenDaysAgo) return false;
          } else if (selectedDateRange === 'LAST_30_DAYS') {
            const thirtyDaysAgo = now.getTime() - 30 * 24 * 60 * 60 * 1000;
            if (reportDate.getTime() < thirtyDaysAgo) return false;
          } else if (selectedDateRange === 'THIS_MONTH') {
            const isThisMonth =
              reportDate.getFullYear() === now.getFullYear() &&
              reportDate.getMonth() === now.getMonth();
            if (!isThisMonth) return false;
          }
        }

        return true;
      })
      .sort((a, b) => {
        if (selectedSortBy === 'OLDEST') {
          const dateA = a.generated_at || a.created_at ? new Date(a.generated_at || a.created_at!).getTime() : 0;
          const dateB = b.generated_at || b.created_at ? new Date(b.generated_at || b.created_at!).getTime() : 0;
          return dateA - dateB;
        }
        if (selectedSortBy === 'ID_ASC') {
          const idA = String(a.inspection_number || a.id || '');
          const idB = String(b.inspection_number || b.id || '');
          return idA.localeCompare(idB, undefined, { numeric: true, sensitivity: 'base' });
        }
        if (selectedSortBy === 'PRODUCT_ASC') {
          const prodA = String(a.product_name || '');
          const prodB = String(b.product_name || '');
          return prodA.localeCompare(prodB, undefined, { sensitivity: 'base' });
        }
        // Default: NEWEST
        const dateA = a.generated_at || a.created_at ? new Date(a.generated_at || a.created_at!).getTime() : 0;
        const dateB = b.generated_at || b.created_at ? new Date(b.generated_at || b.created_at!).getTime() : 0;
        return dateB - dateA;
      });
  }, [reports, searchQuery, selectedCompliance, selectedDateRange, selectedSortBy]);

  const handleDownloadPDF = async (reportItem: ReportItem) => {
    setDownloadingId(reportItem.id);
    try {
      const baseUrl = getApiBaseUrl();
      const pdfUrl = `${baseUrl}/api/inspections/${reportItem.inspection_id}/report/pdf`;
      const token = await authStorage.getToken();

      const localFilename = `LM_Report_${reportItem.inspection_number}_v${reportItem.report_version || 1}.pdf`;

      if (Platform.OS === 'web') {
        const response = await fetch(pdfUrl, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (!response.ok) {
          throw new Error(`Server returned error generating PDF (${response.status})`);
        }
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = localFilename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
        return;
      }

      const fileUri = `${FileSystem.documentDirectory}${localFilename}`;

      const downloadRes = await FileSystem.downloadAsync(pdfUrl, fileUri, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (downloadRes.status === 200) {
        if (await Sharing.isAvailableAsync()) {
          await Sharing.shareAsync(downloadRes.uri, {
            mimeType: 'application/pdf',
            dialogTitle: `Inspection Report: ${reportItem.inspection_number}`,
            UTI: 'com.adobe.pdf',
          });
        } else {
          Alert.alert('Download Saved', `PDF saved to:\n${downloadRes.uri}`);
        }
      }
    } catch (err: any) {
      if (Platform.OS === 'web') {
        alert(err.message || 'Could not download PDF.');
      } else {
        Alert.alert('Export Error', err.message || 'Could not download PDF.');
      }
    } finally {
      setDownloadingId(null);
    }
  };

  const handleShare = async (reportItem: ReportItem) => {
    try {
      const baseUrl = getApiBaseUrl();
      const pdfUrl = `${baseUrl}/api/inspections/${reportItem.inspection_id}/report/pdf`;
      const token = await authStorage.getToken();
      const localFilename = `LM_Report_${reportItem.inspection_number}.pdf`;

      if (Platform.OS === 'web') {
        const response = await fetch(pdfUrl, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (!response.ok) {
          throw new Error(`Server returned error generating PDF (${response.status})`);
        }
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = localFilename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
        return;
      }

      const fileUri = `${FileSystem.documentDirectory}${localFilename}`;

      const downloadRes = await FileSystem.downloadAsync(pdfUrl, fileUri, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (downloadRes.status === 200) {
        if (await Sharing.isAvailableAsync()) {
          await Sharing.shareAsync(downloadRes.uri, {
            mimeType: 'application/pdf',
            dialogTitle: `Share Inspection Report: ${reportItem.inspection_number}`,
            UTI: 'com.adobe.pdf',
          });
        } else {
          Alert.alert('Download Saved', `PDF saved to:\n${downloadRes.uri}`);
        }
      }
    } catch (err: any) {
      if (Platform.OS === 'web') {
        alert(err.message || 'Could not share report.');
      } else {
        Alert.alert('Share Error', err.message || 'Could not share report.');
      }
    }
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        {/* Stitch TopAppBar Header */}
        <View style={styles.topHeader}>
          <TouchableOpacity
            style={styles.headerIconButton}
            onPress={() => navigation.navigate('Dashboard')}
            activeOpacity={0.7}
            accessibilityRole="button"
            accessibilityLabel="Open Menu"
          >
            <MaterialIcons name="menu" size={24} color={colors.onSurfaceVariant} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>NiriKsha</Text>
          <TouchableOpacity
            style={styles.headerIconButton}
            onPress={() => navigation.navigate('Profile')}
            activeOpacity={0.7}
            accessibilityRole="button"
            accessibilityLabel="Navigate to Profile"
          >
            <ProfileAvatar size={36} />
          </TouchableOpacity>
        </View>

        <ScrollView
          contentContainerStyle={styles.scrollContent}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
          showsVerticalScrollIndicator={false}
        >
          {/* Header Title & Search Controls */}
          <View style={styles.pageHeader}>
            <Text style={styles.pageTitle}>Reports</Text>
            <View style={styles.searchRow}>
              <View style={styles.searchContainer}>
                <MaterialIcons name="search" size={20} color={colors.outline} />
                <TextInput
                  style={styles.searchInput}
                  value={searchQuery}
                  onChangeText={setSearchQuery}
                  placeholder="Search reports by ID or Product..."
                  placeholderTextColor={colors.outline}
                />
                {searchQuery.length > 0 && (
                  <TouchableOpacity
                    onPress={() => setSearchQuery('')}
                    hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                  >
                    <MaterialIcons name="clear" size={16} color={colors.outline} />
                  </TouchableOpacity>
                )}
              </View>

              {/* Filters Button */}
              <TouchableOpacity
                style={[styles.filterBtn, activeFilterCount > 0 && styles.filterBtnActive]}
                onPress={handleOpenFilterModal}
                activeOpacity={0.8}
                accessibilityRole="button"
                accessibilityLabel="Filter and sort reports"
              >
                <MaterialIcons
                  name="filter-list"
                  size={18}
                  color={activeFilterCount > 0 ? colors.onPrimary : colors.primary}
                />
                <Text style={[styles.filterBtnText, activeFilterCount > 0 && styles.filterBtnTextActive]}>
                  Filters
                </Text>
                {activeFilterCount > 0 ? (
                  <View style={styles.activeFilterCountBadge}>
                    <Text style={styles.activeFilterCountBadgeText}>{activeFilterCount}</Text>
                  </View>
                ) : (
                  <MaterialIcons name="arrow-drop-down" size={16} color={colors.primary} />
                )}
              </TouchableOpacity>
            </View>

            {/* Active Filter Chips Bar */}
            {activeFilterCount > 0 && (
              <View style={styles.activeFiltersRow}>
                {selectedCompliance !== 'ALL' && (
                  <View style={styles.activeFilterChip}>
                    <Text style={styles.activeFilterChipText}>
                      Status: {selectedCompliance === 'COMPLIANT' ? 'Compliant' : selectedCompliance === 'NON_COMPLIANT' ? 'Non-Compliant' : 'Manual Review'}
                    </Text>
                    <TouchableOpacity
                      onPress={() => setSelectedCompliance('ALL')}
                      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                    >
                      <MaterialIcons name="close" size={14} color={colors.primary} />
                    </TouchableOpacity>
                  </View>
                )}

                {selectedDateRange !== 'ALL' && (
                  <View style={styles.activeFilterChip}>
                    <Text style={styles.activeFilterChipText}>
                      Date: {selectedDateRange === 'TODAY' ? 'Today' : selectedDateRange === 'LAST_7_DAYS' ? 'Last 7 Days' : selectedDateRange === 'LAST_30_DAYS' ? 'Last 30 Days' : 'This Month'}
                    </Text>
                    <TouchableOpacity
                      onPress={() => setSelectedDateRange('ALL')}
                      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                    >
                      <MaterialIcons name="close" size={14} color={colors.primary} />
                    </TouchableOpacity>
                  </View>
                )}

                {selectedSortBy !== 'NEWEST' && (
                  <View style={styles.activeFilterChip}>
                    <Text style={styles.activeFilterChipText}>
                      Sort: {selectedSortBy === 'OLDEST' ? 'Oldest' : selectedSortBy === 'ID_ASC' ? 'ID (A-Z)' : 'Product (A-Z)'}
                    </Text>
                    <TouchableOpacity
                      onPress={() => setSelectedSortBy('NEWEST')}
                      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                    >
                      <MaterialIcons name="close" size={14} color={colors.primary} />
                    </TouchableOpacity>
                  </View>
                )}

                <TouchableOpacity
                  style={styles.clearAllBtn}
                  onPress={handleResetAll}
                >
                  <Text style={styles.clearAllBtnText}>Clear all</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>

          {/* Reports Table Container */}
          <View style={styles.tableContainer}>
            {loading ? (
              <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
            ) : filteredReports.length === 0 ? (
              <View style={styles.emptyBox}>
                <MaterialIcons name="folder-open" size={40} color={colors.outline} />
                <Text style={styles.emptyTitle}>
                  {reports.length === 0 ? 'No Inspection Reports Found' : 'No Reports Match Your Filters'}
                </Text>
                <Text style={styles.emptySubtitle}>
                  {reports.length === 0
                    ? 'Reports generated from finalized inspections will appear here.'
                    : 'Try changing your search query or reset active filters.'}
                </Text>
                {(activeFilterCount > 0 || searchQuery.length > 0) && (
                  <TouchableOpacity
                    style={styles.resetFiltersBtn}
                    onPress={() => {
                      setSearchQuery('');
                      handleResetAll();
                    }}
                    activeOpacity={0.8}
                  >
                    <MaterialIcons name="refresh" size={16} color={colors.primary} />
                    <Text style={styles.resetFiltersBtnText}>Reset Filters & Search</Text>
                  </TouchableOpacity>
                )}
              </View>
            ) : (
              filteredReports.map((item, idx) => {
                const isLast = idx === filteredReports.length - 1;
                const isDownloading = downloadingId === item.id;
                const rawStatus = String(item.overall_status || item.status || '').trim().toUpperCase();

                const isCompliant =
                  rawStatus === 'NO_POTENTIAL_VIOLATIONS' ||
                  rawStatus === 'VERIFIED_COMPLIANT' ||
                  rawStatus === 'COMPLIANT';

                const isNonCompliant =
                  rawStatus === 'POTENTIAL_NON_COMPLIANCE' ||
                  rawStatus === 'FAIL' ||
                  rawStatus === 'NON_COMPLIANT';

                const dateValue = item.generated_at || item.created_at;
                const dateStr = dateValue
                  ? new Date(dateValue).toLocaleDateString('en-GB', {
                      day: 'numeric',
                      month: 'short',
                      year: 'numeric',
                    })
                  : '27 Aug 2026';

                return (
                  <View key={item.id || idx} style={[styles.reportRow, !isLast && styles.rowBorder]}>
                    <View style={styles.rowTop}>
                      <View>
                        <Text style={styles.reportIdText}>{item.inspection_number || item.id}</Text>
                        <Text style={styles.reportDateText}>{dateStr}</Text>
                      </View>
                      <View
                        style={[
                          styles.badge,
                          isCompliant ? styles.badgeGreen : isNonCompliant ? styles.badgeRed : styles.badgeAmber,
                        ]}
                      >
                        <MaterialIcons
                          name={isCompliant ? 'check-circle' : isNonCompliant ? 'error' : 'warning'}
                          size={14}
                          color={
                            isCompliant
                              ? colors.statusGreenText
                              : isNonCompliant
                              ? colors.statusRedText
                              : colors.statusAmberText
                          }
                        />
                        <Text
                          style={[
                            styles.badgeText,
                            {
                              color: isCompliant
                                ? colors.statusGreenText
                                : isNonCompliant
                                ? colors.statusRedText
                                : colors.statusAmberText,
                            },
                          ]}
                        >
                          {isCompliant
                            ? 'No Potential Violations Detected'
                            : isNonCompliant
                            ? 'Potential Non-Compliance Identified'
                            : 'Needs Manual Verification'}
                        </Text>
                      </View>
                    </View>

                    <View style={styles.productDescBox}>
                      <Text style={styles.productNameText}>{item.product_name || 'Packaged Commodity'}</Text>
                      <Text style={styles.productLocationText}>{item.location || 'Field Location'}</Text>
                    </View>

                    <View style={styles.rowActions}>
                      <TouchableOpacity
                        style={styles.actionIconButton}
                        onPress={() =>
                          navigation.navigate('ReportPreview', {
                            inspectionId: item.inspection_id,
                            inspectionNumber: item.inspection_number,
                          })
                        }
                        activeOpacity={0.7}
                        accessibilityRole="button"
                        accessibilityLabel="View Report"
                      >
                        <MaterialIcons name="visibility" size={18} color={colors.primary} />
                      </TouchableOpacity>

                      <TouchableOpacity
                        style={styles.actionIconButton}
                        onPress={() => handleShare(item)}
                        activeOpacity={0.7}
                        accessibilityRole="button"
                        accessibilityLabel="Share Report"
                      >
                        <MaterialIcons name="share" size={18} color={colors.primary} />
                      </TouchableOpacity>

                      <TouchableOpacity
                        style={styles.actionIconButton}
                        onPress={() => handleDownloadPDF(item)}
                        disabled={isDownloading}
                        activeOpacity={0.7}
                        accessibilityRole="button"
                        accessibilityLabel="Download PDF"
                      >
                        {isDownloading ? (
                          <ActivityIndicator size="small" color={colors.primary} />
                        ) : (
                          <MaterialIcons name="download" size={18} color={colors.primary} />
                        )}
                      </TouchableOpacity>
                    </View>
                  </View>
                );
              })
            )}
          </View>
        </ScrollView>

        {/* Filter Modal Panel */}
        <Modal
          visible={filterModalVisible}
          transparent={true}
          animationType="fade"
          onRequestClose={handleCloseModal}
        >
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
            style={styles.modalOverlay}
          >
            <TouchableOpacity
              style={styles.modalBackdropTouchable}
              activeOpacity={1}
              onPress={handleCloseModal}
            />
            <View style={styles.modalContent}>
              {/* Modal Header */}
              <View style={styles.modalHeader}>
                <View>
                  <Text style={styles.modalTitle}>Filter & Sort Reports</Text>
                  <Text style={styles.modalSubtitle}>Refine statutory inspection reports archive</Text>
                </View>
                <TouchableOpacity
                  style={styles.modalCloseBtn}
                  onPress={handleCloseModal}
                  hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                >
                  <MaterialIcons name="close" size={22} color={colors.onSurfaceVariant} />
                </TouchableOpacity>
              </View>

              <ScrollView style={styles.modalBody} showsVerticalScrollIndicator={false}>
                {/* 1. Compliance Status Filter */}
                <View style={styles.filterSection}>
                  <Text style={styles.sectionLabel}>Compliance Status</Text>
                  <View style={styles.chipGrid}>
                    <TouchableOpacity
                      style={[styles.chipItem, tempCompliance === 'ALL' && styles.chipItemActive]}
                      onPress={() => setTempCompliance('ALL')}
                      activeOpacity={0.7}
                    >
                      <MaterialIcons
                        name="list"
                        size={16}
                        color={tempCompliance === 'ALL' ? colors.onPrimary : colors.primary}
                      />
                      <Text style={[styles.chipText, tempCompliance === 'ALL' && styles.chipTextActive]}>
                        All Statuses
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={[styles.chipItem, tempCompliance === 'COMPLIANT' && styles.chipItemActive]}
                      onPress={() => setTempCompliance('COMPLIANT')}
                      activeOpacity={0.7}
                    >
                      <MaterialIcons
                        name="check-circle"
                        size={16}
                        color={tempCompliance === 'COMPLIANT' ? colors.onPrimary : colors.statusGreenText}
                      />
                      <Text style={[styles.chipText, tempCompliance === 'COMPLIANT' && styles.chipTextActive]}>
                        Compliant
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={[styles.chipItem, tempCompliance === 'NON_COMPLIANT' && styles.chipItemActive]}
                      onPress={() => setTempCompliance('NON_COMPLIANT')}
                      activeOpacity={0.7}
                    >
                      <MaterialIcons
                        name="error"
                        size={16}
                        color={tempCompliance === 'NON_COMPLIANT' ? colors.onPrimary : colors.statusRedText}
                      />
                      <Text style={[styles.chipText, tempCompliance === 'NON_COMPLIANT' && styles.chipTextActive]}>
                        Non-Compliant
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={[styles.chipItem, tempCompliance === 'MANUAL_REVIEW' && styles.chipItemActive]}
                      onPress={() => setTempCompliance('MANUAL_REVIEW')}
                      activeOpacity={0.7}
                    >
                      <MaterialIcons
                        name="warning"
                        size={16}
                        color={tempCompliance === 'MANUAL_REVIEW' ? colors.onPrimary : colors.statusAmberText}
                      />
                      <Text style={[styles.chipText, tempCompliance === 'MANUAL_REVIEW' && styles.chipTextActive]}>
                        Manual Review
                      </Text>
                    </TouchableOpacity>
                  </View>
                </View>

                {/* 2. Date Range Filter */}
                <View style={styles.filterSection}>
                  <Text style={styles.sectionLabel}>Date Generated</Text>
                  <View style={styles.chipGrid}>
                    <TouchableOpacity
                      style={[styles.chipItem, tempDateRange === 'ALL' && styles.chipItemActive]}
                      onPress={() => setTempDateRange('ALL')}
                      activeOpacity={0.7}
                    >
                      <MaterialIcons
                        name="date-range"
                        size={16}
                        color={tempDateRange === 'ALL' ? colors.onPrimary : colors.onSurfaceVariant}
                      />
                      <Text style={[styles.chipText, tempDateRange === 'ALL' && styles.chipTextActive]}>
                        All Time
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={[styles.chipItem, tempDateRange === 'TODAY' && styles.chipItemActive]}
                      onPress={() => setTempDateRange('TODAY')}
                      activeOpacity={0.7}
                    >
                      <MaterialIcons
                        name="today"
                        size={16}
                        color={tempDateRange === 'TODAY' ? colors.onPrimary : colors.onSurfaceVariant}
                      />
                      <Text style={[styles.chipText, tempDateRange === 'TODAY' && styles.chipTextActive]}>
                        Today
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={[styles.chipItem, tempDateRange === 'LAST_7_DAYS' && styles.chipItemActive]}
                      onPress={() => setTempDateRange('LAST_7_DAYS')}
                      activeOpacity={0.7}
                    >
                      <MaterialIcons
                        name="event"
                        size={16}
                        color={tempDateRange === 'LAST_7_DAYS' ? colors.onPrimary : colors.onSurfaceVariant}
                      />
                      <Text style={[styles.chipText, tempDateRange === 'LAST_7_DAYS' && styles.chipTextActive]}>
                        Last 7 Days
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={[styles.chipItem, tempDateRange === 'LAST_30_DAYS' && styles.chipItemActive]}
                      onPress={() => setTempDateRange('LAST_30_DAYS')}
                      activeOpacity={0.7}
                    >
                      <MaterialIcons
                        name="calendar-month"
                        size={16}
                        color={tempDateRange === 'LAST_30_DAYS' ? colors.onPrimary : colors.onSurfaceVariant}
                      />
                      <Text style={[styles.chipText, tempDateRange === 'LAST_30_DAYS' && styles.chipTextActive]}>
                        Last 30 Days
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={[styles.chipItem, tempDateRange === 'THIS_MONTH' && styles.chipItemActive]}
                      onPress={() => setTempDateRange('THIS_MONTH')}
                      activeOpacity={0.7}
                    >
                      <MaterialIcons
                        name="calendar-today"
                        size={16}
                        color={tempDateRange === 'THIS_MONTH' ? colors.onPrimary : colors.onSurfaceVariant}
                      />
                      <Text style={[styles.chipText, tempDateRange === 'THIS_MONTH' && styles.chipTextActive]}>
                        This Month
                      </Text>
                    </TouchableOpacity>
                  </View>
                </View>

                {/* 3. Sort Order */}
                <View style={styles.filterSection}>
                  <Text style={styles.sectionLabel}>Sort By</Text>
                  <View style={styles.chipGrid}>
                    <TouchableOpacity
                      style={[styles.chipItem, tempSortBy === 'NEWEST' && styles.chipItemActive]}
                      onPress={() => setTempSortBy('NEWEST')}
                      activeOpacity={0.7}
                    >
                      <MaterialIcons
                        name="schedule"
                        size={16}
                        color={tempSortBy === 'NEWEST' ? colors.onPrimary : colors.onSurfaceVariant}
                      />
                      <Text style={[styles.chipText, tempSortBy === 'NEWEST' && styles.chipTextActive]}>
                        Newest First
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={[styles.chipItem, tempSortBy === 'OLDEST' && styles.chipItemActive]}
                      onPress={() => setTempSortBy('OLDEST')}
                      activeOpacity={0.7}
                    >
                      <MaterialIcons
                        name="history"
                        size={16}
                        color={tempSortBy === 'OLDEST' ? colors.onPrimary : colors.onSurfaceVariant}
                      />
                      <Text style={[styles.chipText, tempSortBy === 'OLDEST' && styles.chipTextActive]}>
                        Oldest First
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={[styles.chipItem, tempSortBy === 'ID_ASC' && styles.chipItemActive]}
                      onPress={() => setTempSortBy('ID_ASC')}
                      activeOpacity={0.7}
                    >
                      <MaterialIcons
                        name="sort-by-alpha"
                        size={16}
                        color={tempSortBy === 'ID_ASC' ? colors.onPrimary : colors.onSurfaceVariant}
                      />
                      <Text style={[styles.chipText, tempSortBy === 'ID_ASC' && styles.chipTextActive]}>
                        Inspection ID
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={[styles.chipItem, tempSortBy === 'PRODUCT_ASC' && styles.chipItemActive]}
                      onPress={() => setTempSortBy('PRODUCT_ASC')}
                      activeOpacity={0.7}
                    >
                      <MaterialIcons
                        name="category"
                        size={16}
                        color={tempSortBy === 'PRODUCT_ASC' ? colors.onPrimary : colors.onSurfaceVariant}
                      />
                      <Text style={[styles.chipText, tempSortBy === 'PRODUCT_ASC' && styles.chipTextActive]}>
                        Product Name
                      </Text>
                    </TouchableOpacity>
                  </View>
                </View>
              </ScrollView>

              {/* Modal Footer Actions */}
              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={styles.modalResetBtn}
                  onPress={handleResetModalFilters}
                  activeOpacity={0.8}
                >
                  <MaterialIcons name="restart-alt" size={16} color={colors.secondary} />
                  <Text style={styles.modalResetText}>Reset All</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.modalApplyBtn}
                  onPress={handleApplyFilters}
                  activeOpacity={0.85}
                >
                  <MaterialIcons name="check" size={16} color={colors.onPrimary} />
                  <Text style={styles.modalApplyText}>Apply Filters</Text>
                </TouchableOpacity>
              </View>
            </View>
          </KeyboardAvoidingView>
        </Modal>

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
  headerIconButton: {
    padding: 6,
    borderRadius: borderRadius.round,
  },
  headerTitle: {
    ...typography.headlineLg,
    fontSize: 18,
    fontWeight: '700',
    color: colors.primary,
  },
  scrollContent: {
    paddingHorizontal: spacing.gutter,
    paddingTop: spacing.stackMd,
    paddingBottom: 90,
    gap: spacing.stackMd,
  },
  pageHeader: {
    gap: spacing.stackSm,
  },
  pageTitle: {
    ...typography.headlineLg,
    fontSize: 20,
    lineHeight: 28,
    fontWeight: '700',
    color: colors.primary,
  },
  searchRow: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'center',
  },
  searchContainer: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    paddingHorizontal: 10,
    paddingVertical: 6,
    gap: 6,
  },
  searchInput: {
    flex: 1,
    ...typography.bodyMd,
    fontSize: 13,
    color: colors.onSurface,
    paddingVertical: 2,
  },
  filterBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    paddingHorizontal: 10,
    paddingVertical: 8,
    gap: 4,
  },
  filterBtnActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  filterBtnText: {
    ...typography.bodyMd,
    fontSize: 13,
    fontWeight: '600',
    color: colors.primary,
  },
  filterBtnTextActive: {
    color: colors.onPrimary,
  },
  activeFilterCountBadge: {
    backgroundColor: colors.statusAmberText,
    width: 18,
    height: 18,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 2,
  },
  activeFilterCountBadgeText: {
    color: '#ffffff',
    fontSize: 10,
    fontWeight: '700',
  },
  activeFiltersRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    alignItems: 'center',
    marginTop: 2,
  },
  activeFilterChip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceContainerHigh,
    borderRadius: borderRadius.lg,
    paddingVertical: 4,
    paddingHorizontal: 8,
    gap: 4,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  activeFilterChipText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.onSurface,
  },
  clearAllBtn: {
    paddingVertical: 4,
    paddingHorizontal: 6,
  },
  clearAllBtnText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '700',
    color: colors.error,
  },
  tableContainer: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    overflow: 'hidden',
  },
  emptyBox: {
    padding: spacing.stackLg,
    alignItems: 'center',
    gap: 8,
  },
  emptyTitle: {
    ...typography.sectionHeader,
    fontSize: 15,
    color: colors.primary,
    textAlign: 'center',
  },
  emptySubtitle: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
    maxWidth: 280,
  },
  resetFiltersBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    paddingVertical: 6,
    paddingHorizontal: 12,
    gap: 6,
    marginTop: 6,
  },
  resetFiltersBtnText: {
    ...typography.bodySm,
    fontSize: 12,
    fontWeight: '600',
    color: colors.primary,
  },
  reportRow: {
    padding: spacing.gutter,
    gap: 8,
  },
  rowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  rowTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 8,
  },
  reportIdText: {
    ...typography.bodySm,
    fontSize: 13,
    fontWeight: '700',
    color: colors.onSurface,
  },
  reportDateText: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
    marginTop: 1,
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: borderRadius.DEFAULT,
    gap: 4,
    maxWidth: '65%',
  },
  badgeGreen: {
    backgroundColor: colors.statusGreenBg,
  },
  badgeRed: {
    backgroundColor: colors.statusRedBg,
  },
  badgeAmber: {
    backgroundColor: colors.statusAmberBg,
  },
  badgeText: {
    ...typography.caption,
    fontSize: 10,
    fontWeight: '600',
  },
  productDescBox: {
    gap: 2,
  },
  productNameText: {
    ...typography.bodyMd,
    fontSize: 14,
    color: colors.onSurface,
  },
  productLocationText: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
  },
  rowActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 8,
    paddingTop: 4,
  },
  actionIconButton: {
    padding: 6,
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
  },

  /* Filter Modal Styles */
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.gutter,
  },
  modalBackdropTouchable: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
  },
  modalContent: {
    width: '100%',
    maxWidth: 440,
    maxHeight: '85%',
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: borderRadius.xl,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.18,
    shadowRadius: 12,
    elevation: 10,
    paddingTop: spacing.gutter,
    paddingBottom: spacing.gutter,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.gutter,
    paddingBottom: spacing.stackSm,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  modalTitle: {
    ...typography.sectionHeader,
    fontSize: 16,
    fontWeight: '700',
    color: colors.primary,
  },
  modalSubtitle: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
    marginTop: 2,
  },
  modalCloseBtn: {
    padding: 4,
    borderRadius: borderRadius.round,
  },
  modalBody: {
    paddingHorizontal: spacing.gutter,
    paddingTop: spacing.stackMd,
  },
  filterSection: {
    marginBottom: spacing.stackLg,
    gap: 8,
  },
  sectionLabel: {
    ...typography.labelCaps,
    fontSize: 11,
    color: colors.primary,
    fontWeight: '700',
  },
  chipGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  chipItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    backgroundColor: colors.surfaceBright,
    gap: 6,
  },
  chipItemActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  chipText: {
    ...typography.bodySm,
    fontSize: 12,
    fontWeight: '500',
    color: colors.onSurface,
  },
  chipTextActive: {
    color: colors.onPrimary,
    fontWeight: '700',
  },
  modalActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: spacing.gutter,
    paddingTop: spacing.stackSm,
    borderTopWidth: 1,
    borderTopColor: colors.borderSubtle,
  },
  modalResetBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    gap: 4,
  },
  modalResetText: {
    ...typography.bodySm,
    fontSize: 12,
    fontWeight: '600',
    color: colors.secondary,
  },
  modalApplyBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.primary,
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: borderRadius.DEFAULT,
    gap: 6,
  },
  modalApplyText: {
    ...typography.bodySm,
    fontSize: 12,
    fontWeight: '700',
    color: colors.onPrimary,
  },
});
