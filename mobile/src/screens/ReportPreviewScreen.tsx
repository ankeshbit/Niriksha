import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  SafeAreaView,
} from 'react-native';
import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { ProfileAvatar } from '../components/ProfileAvatar';
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
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    const fetchReport = async () => {
      try {
        let data = await api.getReportMetadata(inspectionId);
        if (!data || !data.report_number) {
          data = await api.generateReport(inspectionId);
        }
        setReport(data);
      } catch (err) {
        console.error('Failed to load report preview:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchReport();
  }, [inspectionId]);

  const handleDownloadPDF = async () => {
    setDownloading(true);
    try {
      const baseUrl = getApiBaseUrl();
      const pdfUrl = `${baseUrl}/api/inspections/${inspectionId}/report/pdf`;
      const token = await authStorage.getToken();

      const filename = `Inspection_Report_${report?.report_number || inspectionNumber || 'LM-2026'}.pdf`;
      const fileUri = `${FileSystem.documentDirectory}${filename}`;

      const downloadRes = await FileSystem.downloadAsync(pdfUrl, fileUri, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (downloadRes.status === 200) {
        if (await Sharing.isAvailableAsync()) {
          await Sharing.shareAsync(downloadRes.uri, {
            mimeType: 'application/pdf',
            dialogTitle: 'Inspection Report PDF',
            UTI: 'com.adobe.pdf',
          });
        } else {
          Alert.alert('PDF Saved', `Inspection report saved to:\n${downloadRes.uri}`);
        }
      } else {
        Alert.alert('Export Failed', 'Server returned error generating PDF.');
      }
    } catch (err: any) {
      Alert.alert('Export Error', err.message || 'Could not download PDF report.');
    } finally {
      setDownloading(false);
    }
  };

  const status = report?.overall_status || 'POTENTIAL_NON_COMPLIANCE';
  const isCompliant = status === 'NO_POTENTIAL_VIOLATIONS' || status === 'VERIFIED_COMPLIANT';
  const isNonCompliant = status === 'POTENTIAL_NON_COMPLIANCE' || status === 'FAIL';

  const dateStr = report?.generated_at
    ? new Date(report.generated_at).toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
    : new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

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
            <ProfileAvatar size={36} />
          </TouchableOpacity>
        </View>

        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          {/* Back to Inspection Link */}
          <TouchableOpacity
            style={styles.backLink}
            onPress={() => navigation.goBack()}
            activeOpacity={0.7}
          >
            <MaterialIcons name="arrow-back" size={16} color={colors.onSurfaceVariant} />
            <Text style={styles.backLinkText}>BACK TO INSPECTION</Text>
          </TouchableOpacity>

          {loading ? (
            <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 40 }} />
          ) : (
            <View style={styles.paperArticle}>
              {/* Print Header */}
              <View style={styles.printHeader}>
                <View style={styles.balanceCircle}>
                  <MaterialIcons name="balance" size={32} color={colors.primary} />
                </View>
                <Text style={styles.brandTitle}>LEGAL METROLOGY</Text>
                <Text style={styles.reportTitle}>INSPECTION REPORT</Text>
                <Text style={styles.reportSubtitle}>AI-Assisted Legal Metrology Inspection</Text>
                <Text style={styles.prototypeSubtitle}>Smart India Hackathon 2026 Prototype</Text>
                <Text style={styles.versionSubtitle}>Report Version: v{report?.report_version || 1}</Text>
              </View>

              {/* Status Banner */}
              <View
                style={[
                  styles.statusBanner,
                  isCompliant
                    ? styles.statusBannerGreen
                    : isNonCompliant
                    ? styles.statusBannerAmber
                    : styles.statusBannerAmber,
                ]}
              >
                <MaterialIcons
                  name={isCompliant ? 'check-circle' : 'warning'}
                  size={20}
                  color={isCompliant ? colors.statusGreenText : colors.statusAmberText}
                />
                <Text
                  style={[
                    styles.statusBannerText,
                    { color: isCompliant ? colors.statusGreenText : colors.statusAmberText },
                  ]}
                >
                  {isCompliant
                    ? 'NO POTENTIAL VIOLATIONS DETECTED'
                    : 'POTENTIAL NON-COMPLIANCE IDENTIFIED'}
                </Text>
              </View>

              {/* Statutory Note */}
              <View style={styles.statutoryNote}>
                <MaterialIcons name="info" size={14} color={colors.onSurfaceVariant} style={{ marginTop: 1 }} />
                <Text style={styles.statutoryNoteText}>
                  This report covers a limited set of machine-verifiable Legal Metrology requirements only. Final legal determination rests with the authorized inspecting officer.
                </Text>
              </View>

              {/* Details Section */}
              <View style={styles.detailsGrid}>
                <View style={styles.detailItem}>
                  <Text style={styles.detailLabel}>INSPECTION ID</Text>
                  <Text style={styles.detailValueBold}>
                    {report?.inspection_number || inspectionNumber || 'LM-2026-00891'}
                  </Text>
                </View>
                <View style={styles.detailItem}>
                  <Text style={styles.detailLabel}>DATE</Text>
                  <Text style={styles.detailValue}>{dateStr}</Text>
                </View>
                <View style={styles.detailItem}>
                  <Text style={styles.detailLabel}>PRODUCT</Text>
                  <Text style={styles.detailValue}>{report?.product_name || 'Premium Basmati Rice'}</Text>
                </View>
                <View style={styles.detailItem}>
                  <Text style={styles.detailLabel}>LOCATION</Text>
                  <Text style={styles.detailValue}>{report?.location || 'Sector 4 Market'}</Text>
                </View>
                <View style={styles.detailItem}>
                  <Text style={styles.detailLabel}>MANUFACTURER</Text>
                  <Text style={styles.detailValue}>{report?.manufacturer || report?.product_name || '—'}</Text>
                </View>
              </View>

              {/* Action Buttons */}
              <View style={styles.actionsBox}>
                <TouchableOpacity
                  style={styles.downloadPdfBtn}
                  onPress={handleDownloadPDF}
                  disabled={downloading}
                  activeOpacity={0.85}
                >
                  {downloading ? (
                    <ActivityIndicator size="small" color={colors.onPrimary} />
                  ) : (
                    <View style={styles.btnRow}>
                      <MaterialIcons name="download" size={18} color={colors.onPrimary} />
                      <Text style={styles.downloadPdfText}>Download Signed PDF Report</Text>
                    </View>
                  )}
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.doneBtn}
                  onPress={() => navigation.navigate('Dashboard')}
                  activeOpacity={0.85}
                >
                  <Text style={styles.doneBtnText}>Return to Dashboard</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}

          <View style={{ height: 20 }} />
        </ScrollView>
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
    paddingBottom: 40,
    gap: spacing.stackMd,
  },
  backLink: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginBottom: 4,
  },
  backLinkText: {
    ...typography.labelCaps,
    fontSize: 12,
    color: colors.onSurfaceVariant,
    fontWeight: '600',
  },
  paperArticle: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    overflow: 'hidden',
  },
  printHeader: {
    padding: 24,
    alignItems: 'center',
    backgroundColor: colors.surfaceBright,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  balanceCircle: {
    width: 60,
    height: 60,
    borderRadius: 30,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
  },
  brandTitle: {
    ...typography.headlineLg,
    fontSize: 20,
    fontWeight: '800',
    color: colors.primary,
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  reportTitle: {
    ...typography.sectionHeader,
    fontSize: 16,
    fontWeight: '700',
    color: colors.primary,
    letterSpacing: 0.5,
    marginTop: 2,
    textTransform: 'uppercase',
  },
  reportSubtitle: {
    ...typography.bodySm,
    fontSize: 13,
    color: colors.onSurfaceVariant,
    marginTop: 4,
  },
  prototypeSubtitle: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
    fontStyle: 'italic',
    marginTop: 2,
  },
  versionSubtitle: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
    marginTop: 2,
  },
  statusBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    paddingHorizontal: spacing.gutter,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    gap: 8,
  },
  statusBannerGreen: {
    backgroundColor: colors.statusGreenBg,
  },
  statusBannerAmber: {
    backgroundColor: colors.statusAmberBg,
  },
  statusBannerText: {
    ...typography.sectionHeader,
    fontSize: 14,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  statutoryNote: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: 'rgba(218, 224, 233, 0.3)',
    padding: spacing.stackSm,
    gap: 6,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  statutoryNoteText: {
    ...typography.caption,
    fontSize: 11,
    lineHeight: 15,
    color: colors.onSurfaceVariant,
    flex: 1,
  },
  detailsGrid: {
    padding: spacing.gutter,
    gap: 12,
  },
  detailItem: {
    gap: 2,
    borderBottomWidth: 1,
    borderBottomColor: colors.surfaceContainerHigh,
    paddingBottom: 8,
  },
  detailLabel: {
    ...typography.labelCaps,
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
  detailValue: {
    ...typography.bodyMd,
    fontSize: 14,
    color: colors.onSurface,
  },
  detailValueBold: {
    ...typography.bodyMd,
    fontSize: 14,
    fontWeight: '700',
    color: colors.primary,
  },
  actionsBox: {
    padding: spacing.gutter,
    gap: 10,
    backgroundColor: colors.surfaceContainerLow,
    borderTopWidth: 1,
    borderTopColor: colors.borderSubtle,
  },
  downloadPdfBtn: {
    backgroundColor: colors.primary,
    paddingVertical: 12,
    borderRadius: borderRadius.DEFAULT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  downloadPdfText: {
    ...typography.sectionHeader,
    fontSize: 14,
    color: colors.onPrimary,
    fontWeight: '600',
  },
  doneBtn: {
    paddingVertical: 10,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: borderRadius.DEFAULT,
  },
  doneBtnText: {
    ...typography.bodySm,
    fontSize: 13,
    color: colors.primary,
    fontWeight: '600',
  },
});
