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
} from 'react-native';
import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { AppHeader } from '../components/AppHeader';
import { BottomNav } from '../components/BottomNav';
import { StatusBadge } from '../components/StatusBadge';
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
          Alert.alert('Download Saved', `PDF saved to: ${downloadRes.uri}`);
        }
      }
    } catch (err: any) {
      Alert.alert('Export Error', err.message || 'Could not download PDF.');
    } finally {
      setDownloadingId(null);
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
    <View style={styles.container}>
      <AppHeader
        title="REPORTS ARCHIVE"
        subtitle="Department of Consumer Affairs (DoCA)"
        showBack={false}
      />

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        {/* Search Bar */}
        <View style={styles.searchContainer}>
          <MaterialIcons name="search" size={20} color={colors.onSurfaceVariant} />
          <TextInput
            style={styles.searchInput}
            value={searchQuery}
            onChangeText={setSearchQuery}
            placeholder="Search by ID, commodity, or site..."
            placeholderTextColor={colors.outline}
          />
          {searchQuery ? (
            <TouchableOpacity onPress={() => setSearchQuery('')}>
              <MaterialIcons name="clear" size={18} color={colors.onSurfaceVariant} />
            </TouchableOpacity>
          ) : null}
        </View>

        {loading ? (
          <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
        ) : filteredReports.length === 0 ? (
          <View style={styles.emptyCard}>
            <MaterialIcons name="folder-open" size={40} color={colors.outline} />
            <Text style={styles.emptyTitle}>No Inspection Reports Found</Text>
            <Text style={styles.emptySub}>
              Reports generated from finalized inspections will appear here.
            </Text>
          </View>
        ) : (
          filteredReports.map((item) => {
            const isDownloading = downloadingId === item.id;
            const dateStr = item.generated_at
              ? new Date(item.generated_at).toLocaleDateString('en-GB', {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                })
              : 'Recent';

            return (
              <View key={item.id} style={styles.reportCard}>
                <View style={styles.cardHeader}>
                  <View>
                    <Text style={styles.inspNumText}>{item.inspection_number}</Text>
                    <Text style={styles.dateVersionText}>
                      {dateStr} • Version {item.report_version || 1}
                    </Text>
                  </View>
                  <StatusBadge status={item.overall_status} />
                </View>

                <View style={styles.bodySection}>
                  <Text style={styles.productNameText}>{item.product_name || 'Packaged Commodity'}</Text>
                  <Text style={styles.locationText}>{item.location || 'Field Location'}</Text>
                </View>

                <View style={styles.cardActionsRow}>
                  <TouchableOpacity
                    style={styles.previewBtn}
                    onPress={() =>
                      navigation.navigate('ReportPreview', {
                        inspectionId: item.inspection_id,
                        inspectionNumber: item.inspection_number,
                      })
                    }
                    activeOpacity={0.8}
                  >
                    <MaterialIcons name="visibility" size={16} color={colors.primary} />
                    <Text style={styles.previewBtnText}>View Summary</Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    style={styles.pdfBtn}
                    onPress={() => handleDownloadPDF(item)}
                    disabled={isDownloading}
                    activeOpacity={0.8}
                  >
                    {isDownloading ? (
                      <ActivityIndicator size="small" color={colors.onPrimary} />
                    ) : (
                      <>
                        <MaterialIcons name="download" size={16} color={colors.onPrimary} />
                        <Text style={styles.pdfBtnText}>Download PDF</Text>
                      </>
                    )}
                  </TouchableOpacity>
                </View>
              </View>
            );
          })
        )}
      </ScrollView>

      <BottomNav />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.surface,
  },
  scrollContent: {
    padding: spacing.gutter,
    paddingBottom: 24,
    gap: spacing.stackMd,
  },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceBright,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    paddingHorizontal: 12,
    paddingVertical: 6,
    gap: 8,
  },
  searchInput: {
    ...typography.bodyMd,
    flex: 1,
    color: colors.onSurface,
    paddingVertical: 2,
  },
  emptyCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.stackLg,
    alignItems: 'center',
    gap: 8,
    marginTop: 20,
  },
  emptyTitle: {
    ...typography.sectionHeader,
    color: colors.primary,
  },
  emptySub: {
    ...typography.bodySm,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
  },
  reportCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.marginX,
    gap: spacing.stackSm,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
  },
  inspNumText: {
    ...typography.bodyMdMedium,
    color: colors.primary,
    fontWeight: '700',
  },
  dateVersionText: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
    marginTop: 1,
  },
  bodySection: {
    gap: 2,
  },
  productNameText: {
    ...typography.bodyMdMedium,
    color: colors.onSurface,
  },
  locationText: {
    ...typography.bodySm,
    color: colors.onSurfaceVariant,
  },
  cardActionsRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: colors.surfaceContainerHigh,
  },
  previewBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
    paddingHorizontal: 12,
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    gap: 4,
  },
  previewBtnText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.primary,
  },
  pdfBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
    paddingHorizontal: 12,
    backgroundColor: colors.primary,
    borderRadius: borderRadius.lg,
    gap: 4,
  },
  pdfBtnText: {
    ...typography.caption,
    fontWeight: '700',
    color: colors.onPrimary,
  },
});
