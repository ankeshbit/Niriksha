import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  Platform,
} from 'react-native';
import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { AppHeader } from '../components/AppHeader';
import { StatusBadge } from '../components/StatusBadge';
import { api, getApiBaseUrl } from '../services/api';
import { authStorage } from '../services/authStorage';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const ReportPreviewScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'ReportPreview'>>();
  const { inspectionId, inspectionNumber } = route.params;

  const [report, setReport] = useState<any | null>(null);
  const [inspection, setInspection] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    const loadReport = async () => {
      try {
        const [rep, insp] = await Promise.all([
          api.getReportMetadata(inspectionId),
          api.getInspection(inspectionId),
        ]);
        setReport(rep);
        setInspection(insp);
      } catch (err) {
        console.error('Failed to load report preview:', err);
      } finally {
        setLoading(false);
      }
    };

    loadReport();
  }, [inspectionId]);

  const handleDownloadAndSharePDF = async () => {
    setDownloading(true);
    try {
      const baseUrl = getApiBaseUrl();
      const pdfUrl = `${baseUrl}/api/inspections/${inspectionId}/report/pdf`;
      const token = await authStorage.getToken();

      const localFilename = `LM_Report_${inspection?.inspection_number || inspectionNumber || 'doc'}.pdf`;
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
            dialogTitle: `Official Statutory Inspection Report: ${inspection?.inspection_number}`,
            UTI: 'com.adobe.pdf',
          });
        } else {
          Alert.alert('Download Complete', `Report saved to: ${downloadRes.uri}`);
        }
      } else {
        throw new Error(`Download failed with HTTP ${downloadRes.status}`);
      }
    } catch (err: any) {
      Alert.alert('PDF Export Error', err.message || 'Could not download PDF report.');
    } finally {
      setDownloading(false);
    }
  };

  const generatedDateStr = report?.generated_at
    ? new Date(report.generated_at).toLocaleString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : new Date().toLocaleString('en-GB');

  return (
    <View style={styles.container}>
      <AppHeader
        title="INSPECTION REPORT"
        subtitle={`Verified Record: ${inspection?.inspection_number || inspectionNumber || 'LM-2026'}`}
        showBack={true}
        onBackPress={() => navigation.navigate('Dashboard')}
      />

      <ScrollView contentContainerStyle={styles.scrollContent}>
        {loading ? (
          <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
        ) : (
          <>
            {/* Success Status Banner */}
            <View style={styles.successBanner}>
              <MaterialIcons name="verified" size={24} color={colors.statusGreenText} />
              <View style={{ flex: 1 }}>
                <Text style={styles.successTitle}>Official Inspection Report Generated</Text>
                <Text style={styles.successSubtext}>
                  Compiled from verified database records under PCR 2011.
                </Text>
              </View>
            </View>

            {/* Report Metadata Card */}
            <View style={styles.card}>
              <View style={styles.cardTop}>
                <Text style={styles.reportDocTitle}>LEGAL METROLOGY INSPECTION REPORT</Text>
                <View style={styles.versionBadge}>
                  <Text style={styles.versionText}>Version {report?.report_version || 1}</Text>
                </View>
              </View>

              <View style={styles.divider} />

              <View style={styles.metaGrid}>
                <View style={styles.metaRow}>
                  <Text style={styles.metaLabel}>Inspection Number:</Text>
                  <Text style={styles.metaValueBold}>{inspection?.inspection_number}</Text>
                </View>

                <View style={styles.metaRow}>
                  <Text style={styles.metaLabel}>Packaged Commodity:</Text>
                  <Text style={styles.metaValue}>{inspection?.product?.product_name}</Text>
                </View>

                <View style={styles.metaRow}>
                  <Text style={styles.metaLabel}>Location Site:</Text>
                  <Text style={styles.metaValue}>{inspection?.location}</Text>
                </View>

                <View style={styles.metaRow}>
                  <Text style={styles.metaLabel}>Inspection Status:</Text>
                  <StatusBadge status={inspection?.overall_status} />
                </View>

                <View style={styles.metaRow}>
                  <Text style={styles.metaLabel}>Generated On:</Text>
                  <Text style={styles.metaValue}>{generatedDateStr}</Text>
                </View>
              </View>

              <View style={styles.divider} />

              {/* Safety Notice */}
              <Text style={styles.safetyStatement}>
                {report?.legal_safety_statement ||
                  'Official inspection record generated under statutory human authority of the designated inspecting officer.'}
              </Text>
            </View>

            {/* Legal Disclaimer — PRD Required */}
            {inspection?.overall_status === 'NO_POTENTIAL_VIOLATIONS' && (
              <View style={styles.disclaimerCard}>
                <MaterialIcons name="info" size={18} color={colors.primary} />
                <Text style={styles.disclaimerText}>
                  The implemented machine-verifiable checks did not identify a potential issue based on the available evidence. This is not a certification of full legal compliance.
                </Text>
              </View>
            )}

            {/* Action Buttons */}
            <TouchableOpacity
              style={styles.downloadButton}
              onPress={handleDownloadAndSharePDF}
              disabled={downloading}
              activeOpacity={0.85}
            >
              {downloading ? (
                <ActivityIndicator size="small" color={colors.onPrimary} />
              ) : (
                <View style={styles.btnInner}>
                  <MaterialIcons name="download" size={20} color={colors.onPrimary} />
                  <Text style={styles.downloadButtonText}>Download & View PDF Report</Text>
                </View>
              )}
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.archiveNavButton}
              onPress={() => navigation.navigate('ReportsList')}
              activeOpacity={0.8}
            >
              <MaterialIcons name="folder" size={18} color={colors.primary} />
              <Text style={styles.archiveNavText}>View in Reports Archive</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.dashboardButton}
              onPress={() => navigation.navigate('Dashboard')}
              activeOpacity={0.8}
            >
              <Text style={styles.dashboardButtonText}>Return to Dashboard</Text>
            </TouchableOpacity>
          </>
        )}
      </ScrollView>
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
    paddingBottom: 32,
    gap: spacing.stackMd,
  },
  successBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.statusGreenBg,
    borderWidth: 1,
    borderColor: colors.statusGreenText,
    borderRadius: borderRadius.lg,
    padding: spacing.marginX,
    gap: 12,
  },
  successTitle: {
    ...typography.bodyMdMedium,
    color: colors.statusGreenText,
    fontWeight: '700',
  },
  successSubtext: {
    ...typography.caption,
    color: colors.statusGreenText,
    marginTop: 2,
  },
  card: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.marginX,
    gap: spacing.stackSm,
  },
  cardTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  reportDocTitle: {
    ...typography.sectionHeader,
    fontSize: 14,
    color: colors.primary,
    flex: 1,
  },
  versionBadge: {
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: borderRadius.sm,
  },
  versionText: {
    ...typography.caption,
    fontWeight: '700',
    color: colors.primary,
  },
  divider: {
    height: 1,
    backgroundColor: colors.surfaceContainerHigh,
  },
  metaGrid: {
    gap: 6,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  metaLabel: {
    ...typography.caption,
    color: colors.onSurfaceVariant,
    fontWeight: '600',
  },
  metaValue: {
    ...typography.bodySm,
    color: colors.onSurface,
  },
  metaValueBold: {
    ...typography.bodyMdMedium,
    color: colors.primary,
  },
  safetyStatement: {
    ...typography.caption,
    fontSize: 10,
    lineHeight: 14,
    color: colors.outline,
    fontStyle: 'italic',
  },
  downloadButton: {
    backgroundColor: colors.primary,
    paddingVertical: 14,
    borderRadius: borderRadius.lg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  downloadButtonText: {
    ...typography.sectionHeader,
    color: colors.onPrimary,
  },
  archiveNavButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    gap: 6,
  },
  archiveNavText: {
    ...typography.sectionHeader,
    fontSize: 14,
    color: colors.primary,
  },
  dashboardButton: {
    alignItems: 'center',
    paddingVertical: 8,
  },
  dashboardButtonText: {
    ...typography.bodySm,
    color: colors.onSurfaceVariant,
  },
  disclaimerCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    padding: spacing.stackMd,
    backgroundColor: '#e8f0fe',
    borderWidth: 1,
    borderColor: colors.primary,
    borderRadius: borderRadius.lg,
  },
  disclaimerText: {
    ...typography.caption,
    color: colors.primary,
    flex: 1,
    lineHeight: 16,
    fontStyle: 'italic',
  },
});
