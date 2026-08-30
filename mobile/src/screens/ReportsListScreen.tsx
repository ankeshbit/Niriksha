import React, { useState, useEffect, useCallback } from 'react';
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

export const ReportsListScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [reports, setReports] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const loadReports = async () => {
    try {
      const data = await api.getReportsList();
      setReports(data || []);
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

  const handleDownloadPDF = async (reportItem: any) => {
    setDownloadingId(reportItem.id);
    try {
      const baseUrl = getApiBaseUrl();
      const pdfUrl = `${baseUrl}/api/inspections/${reportItem.inspection_id}/report/pdf`;
      const token = await authStorage.getToken();

      const localFilename = `LM_Report_${reportItem.inspection_number}_v${reportItem.report_version || 1}.pdf`;
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
      Alert.alert('Export Error', err.message || 'Could not download PDF.');
    } finally {
      setDownloadingId(null);
    }
  };

  const handleShare = async (reportItem: any) => {
    try {
      const baseUrl = getApiBaseUrl();
      const pdfUrl = `${baseUrl}/api/inspections/${reportItem.inspection_id}/report/pdf`;
      const token = await authStorage.getToken();
      const localFilename = `LM_Report_${reportItem.inspection_number}.pdf`;
      const fileUri = `${FileSystem.documentDirectory}${localFilename}`;

      const downloadRes = await FileSystem.downloadAsync(pdfUrl, fileUri, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (downloadRes.status === 200 && (await Sharing.isAvailableAsync())) {
        await Sharing.shareAsync(downloadRes.uri);
      }
    } catch (err: any) {
      Alert.alert('Share Error', err.message || 'Could not share report.');
    }
  };

  const filteredReports = reports.filter((r) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      r.inspection_number?.toLowerCase().includes(q) ||
      r.product_name?.toLowerCase().includes(q) ||
      r.location?.toLowerCase().includes(q)
    );
  });

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        {/* Stitch TopAppBar Header */}
        <View style={styles.topHeader}>
          <TouchableOpacity
            style={styles.headerIconButton}
            onPress={() => navigation.navigate('Dashboard')}
            activeOpacity={0.7}
          >
            <MaterialIcons name="menu" size={24} color={colors.onSurfaceVariant} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>LEGAL METROLOGY</Text>
          <TouchableOpacity
            style={styles.headerIconButton}
            onPress={() => navigation.navigate('Profile')}
            activeOpacity={0.7}
            accessibilityRole="button"
            accessibilityLabel="Navigate to Profile"
          >
            <ProfileAvatar size={28} />
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
              </View>
              <TouchableOpacity style={styles.filterBtn} activeOpacity={0.8}>
                <MaterialIcons name="filter-list" size={18} color={colors.primary} />
                <Text style={styles.filterBtnText}>Filters</Text>
                <MaterialIcons name="arrow-drop-down" size={16} color={colors.primary} />
              </TouchableOpacity>
            </View>
          </View>

          {/* Reports Table Container */}
          <View style={styles.tableContainer}>
            {loading ? (
              <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
            ) : filteredReports.length === 0 ? (
              <View style={styles.emptyBox}>
                <MaterialIcons name="folder-open" size={40} color={colors.outline} />
                <Text style={styles.emptyTitle}>No Inspection Reports Found</Text>
                <Text style={styles.emptySubtitle}>
                  Reports generated from finalized inspections will appear here.
                </Text>
              </View>
            ) : (
              filteredReports.map((item, idx) => {
                const isLast = idx === filteredReports.length - 1;
                const isDownloading = downloadingId === item.id;
                const isNonCompliant =
                  item.overall_status === 'POTENTIAL_NON_COMPLIANCE' || item.overall_status === 'FAIL';
                const isCompliant =
                  item.overall_status === 'NO_POTENTIAL_VIOLATIONS' || item.overall_status === 'VERIFIED_COMPLIANT';

                const dateStr = item.generated_at
                  ? new Date(item.generated_at).toLocaleDateString('en-GB', {
                      day: 'numeric',
                      month: 'short',
                      year: 'numeric',
                    })
                  : '27 Aug 2026';

                return (
                  <View key={item.id || idx} style={[styles.reportRow, !isLast && styles.rowBorder]}>
                    <View style={styles.rowTop}>
                      <View>
                        <Text style={styles.reportIdText}>{item.inspection_number}</Text>
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
                      >
                        <MaterialIcons name="visibility" size={18} color={colors.primary} />
                      </TouchableOpacity>

                      <TouchableOpacity
                        style={styles.actionIconButton}
                        onPress={() => handleShare(item)}
                        activeOpacity={0.7}
                      >
                        <MaterialIcons name="share" size={18} color={colors.primary} />
                      </TouchableOpacity>

                      <TouchableOpacity
                        style={styles.actionIconButton}
                        onPress={() => handleDownloadPDF(item)}
                        disabled={isDownloading}
                        activeOpacity={0.7}
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
  filterBtnText: {
    ...typography.bodyMd,
    fontSize: 13,
    color: colors.primary,
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
  },
  emptySubtitle: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
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
});
