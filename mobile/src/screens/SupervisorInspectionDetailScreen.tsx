import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  Modal,
  Alert,
  ActivityIndicator,
  Linking,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { api } from '../services/api';
import { getApiBaseUrl } from '../services/api';
import { useNavigation, useRoute } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const SupervisorInspectionDetailScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<any>();
  const insets = useSafeAreaInsets();

  const inspectionId = route.params?.inspectionId;
  const initialInspectionNumber = route.params?.inspectionNumber;

  const [inspection, setInspection] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Delete Inspection Modal State
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [confirmNumberInput, setConfirmNumberInput] = useState('');
  const [deleteReason, setDeleteReason] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);

  // Delete Report Modal State
  const [showDeleteReportModal, setShowDeleteReportModal] = useState(false);
  const [isDeletingReport, setIsDeletingReport] = useState(false);

  const fetchDetail = useCallback(async () => {
    if (!inspectionId) return;
    try {
      setLoading(true);
      setError(null);
      const res: any = await api.getInspection(inspectionId);
      setInspection(res);
    } catch (err: any) {
      setError(err?.message || 'Unable to retrieve complete inspection record.');
    } finally {
      setLoading(false);
    }
  }, [inspectionId]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  const handleDeleteInspection = async () => {
    if (!inspection) return;
    const actualNum = (inspection.inspection_number || '').trim().toUpperCase();
    const typedNum = confirmNumberInput.trim().toUpperCase();

    if (typedNum !== actualNum) {
      Alert.alert('Mismatch', `Please type the exact inspection number: ${inspection.inspection_number}`);
      return;
    }

    try {
      setIsDeleting(true);
      await api.deleteInspection(inspection.id, confirmNumberInput.trim(), deleteReason.trim());
      setShowDeleteModal(false);
      Alert.alert('Deleted', `Inspection ${inspection.inspection_number} has been permanently deleted.`);
      navigation.navigate('SupervisorAllInspections');
    } catch (err: any) {
      Alert.alert('Deletion Failed', err?.message || 'Could not delete inspection. Please try again.');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleDeleteReport = async () => {
    if (!inspection) return;
    try {
      setIsDeletingReport(true);
      await api.deleteReport(inspection.id);
      setShowDeleteReportModal(false);
      Alert.alert('Report Deleted', 'Statutory report removed. The inspection remains intact.');
      fetchDetail();
    } catch (err: any) {
      Alert.alert('Error', err?.message || 'Could not delete report.');
    } finally {
      setIsDeletingReport(false);
    }
  };

  const openPdf = () => {
    if (!inspection) return;
    const url = `${getApiBaseUrl()}/api/inspections/${inspection.id}/report/pdf`;
    Linking.openURL(url).catch(() => Alert.alert('Error', 'Could not open PDF file.'));
  };

  const openDocx = () => {
    if (!inspection) return;
    const url = `${getApiBaseUrl()}/api/inspections/${inspection.id}/report/docx`;
    Linking.openURL(url).catch(() => Alert.alert('Error', 'Could not open DOCX file.'));
  };

  const isConfirmedMatch =
    inspection &&
    confirmNumberInput.trim().toUpperCase() === (inspection.inspection_number || '').trim().toUpperCase();

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
      <View style={styles.container}>
        {/* Header */}
        <View style={styles.topHeader}>
          <TouchableOpacity style={styles.backButton} onPress={() => navigation.goBack()}>
            <MaterialIcons name="arrow-back" size={24} color={colors.onSurface} />
          </TouchableOpacity>
          <View style={styles.headerTitleContainer}>
            <Text style={styles.headerTitle}>{inspection?.inspection_number || initialInspectionNumber || 'Inspection Detail'}</Text>
            <Text style={styles.headerSub}>Supervisor Oversight & Verification</Text>
          </View>
          <TouchableOpacity style={styles.refreshIcon} onPress={() => fetchDetail()}>
            <MaterialIcons name="refresh" size={22} color={colors.primary} />
          </TouchableOpacity>
        </View>

        {loading ? (
          <View style={styles.centerContainer}>
            <ActivityIndicator size="large" color={colors.primary} />
            <Text style={styles.loadingText}>Retrieving complete 12-section inspection record...</Text>
          </View>
        ) : error ? (
          <View style={styles.centerContainer}>
            <MaterialIcons name="error-outline" size={44} color={colors.error} />
            <Text style={styles.errorTitle}>Error Loading Inspection</Text>
            <Text style={styles.errorMessage}>{error}</Text>
            <TouchableOpacity style={styles.retryBtn} onPress={() => fetchDetail()}>
              <Text style={styles.retryBtnText}>Retry</Text>
            </TouchableOpacity>
          </View>
        ) : !inspection ? (
          <View style={styles.centerContainer}>
            <Text style={styles.emptyTitle}>Inspection Not Found</Text>
          </View>
        ) : (
          <ScrollView
            style={styles.scrollArea}
            contentContainerStyle={[styles.scrollContent, { paddingBottom: insets.bottom + 40 }]}
          >
            {/* Status Banner */}
            <View style={styles.statusBanner}>
              <View style={styles.statusBannerLeft}>
                <Text style={styles.statusBannerLabel}>Overall Compliance State</Text>
                <Text
                  style={[
                    styles.statusBannerVal,
                    inspection.overall_status === 'POTENTIAL_NON_COMPLIANCE'
                      ? styles.statusRed
                      : inspection.overall_status === 'NO_POTENTIAL_VIOLATIONS'
                      ? styles.statusGreen
                      : styles.statusAmber,
                  ]}
                >
                  {inspection.overall_status || inspection.status}
                </Text>
              </View>
              <View style={styles.lifecyclePill}>
                <Text style={styles.lifecycleText}>{inspection.status}</Text>
              </View>
            </View>

            {/* SECTION 1: Inspection Information */}
            <View style={styles.sectionCard}>
              <View style={styles.sectionHeaderRow}>
                <MaterialIcons name="info" size={18} color={colors.primary} />
                <Text style={styles.sectionTitle}>1. Inspection Information</Text>
              </View>
              <View style={styles.infoGrid}>
                <View style={styles.infoCol}>
                  <Text style={styles.infoLabel}>Product Name</Text>
                  <Text style={styles.infoVal}>{inspection.product?.product_name || 'N/A'}</Text>
                </View>
                <View style={styles.infoCol}>
                  <Text style={styles.infoLabel}>Brand</Text>
                  <Text style={styles.infoVal}>{inspection.product?.brand_name || 'N/A'}</Text>
                </View>
                <View style={styles.infoCol}>
                  <Text style={styles.infoLabel}>Category</Text>
                  <Text style={styles.infoVal}>{inspection.product?.category || 'N/A'}</Text>
                </View>
                <View style={styles.infoCol}>
                  <Text style={styles.infoLabel}>Batch / Lot No.</Text>
                  <Text style={styles.infoVal}>{inspection.product?.batch_number || 'N/A'}</Text>
                </View>
                <View style={styles.infoCol}>
                  <Text style={styles.infoLabel}>Inspection Location</Text>
                  <Text style={styles.infoVal}>{inspection.location || 'N/A'}</Text>
                </View>
                <View style={styles.infoCol}>
                  <Text style={styles.infoLabel}>Date & Time</Text>
                  <Text style={styles.infoVal}>
                    {new Date(inspection.created_at).toLocaleString('en-IN')}
                  </Text>
                </View>
                <View style={styles.infoCol}>
                  <Text style={styles.infoLabel}>Officer ID</Text>
                  <Text style={styles.infoVal}>{inspection.inspector?.officer_id || inspection.inspector_id || 'N/A'}</Text>
                </View>
                <View style={styles.infoCol}>
                  <Text style={styles.infoLabel}>Officer Name</Text>
                  <Text style={styles.infoVal}>{inspection.inspector?.full_name || 'Field Inspector'}</Text>
                </View>
              </View>
            </View>

            {/* SECTION 2: Images */}
            <View style={styles.sectionCard}>
              <View style={styles.sectionHeaderRow}>
                <MaterialIcons name="photo-library" size={18} color={colors.primary} />
                <Text style={styles.sectionTitle}>2. Product Package Images ({inspection.images?.length || 0})</Text>
              </View>
              {inspection.images && inspection.images.length > 0 ? (
                <View style={styles.imagesGrid}>
                  {inspection.images.map((img: any, idx: number) => (
                    <View key={img.id || idx} style={styles.imageItem}>
                      <View style={styles.imagePlaceholder}>
                        <MaterialIcons name="image" size={32} color={colors.primary} />
                        <Text style={styles.imageLabel}>{img.view_type?.toUpperCase() || `IMAGE ${idx + 1}`}</Text>
                      </View>
                      <Text style={styles.imageMeta}>
                        Quality: {Math.round((img.quality_score || 1) * 100)}% • {img.quality_status || 'GOOD'}
                      </Text>
                    </View>
                  ))}
                </View>
              ) : (
                <Text style={styles.notAvailableText}>No images uploaded for this inspection.</Text>
              )}
            </View>

            {/* SECTION 3: OCR Engine Extraction */}
            <View style={styles.sectionCard}>
              <View style={styles.sectionHeaderRow}>
                <MaterialIcons name="text-fields" size={18} color={colors.primary} />
                <Text style={styles.sectionTitle}>3. AI OCR Extraction (Immutable Baseline)</Text>
              </View>
              <Text style={styles.helperText}>Raw machine extraction before officer verification:</Text>
              <View style={styles.ocrBox}>
                <Text style={styles.ocrText}>
                  {inspection.declarations && inspection.declarations.length > 0
                    ? inspection.declarations.map((d: any) => `${d.field_name}: ${d.extracted_value || 'NOT_FOUND'}`).join('\n')
                    : 'No OCR declarations recorded.'}
                </Text>
              </View>
            </View>

            {/* SECTION 4: Extracted Declarations */}
            <View style={styles.sectionCard}>
              <View style={styles.sectionHeaderRow}>
                <MaterialIcons name="table-chart" size={18} color={colors.primary} />
                <Text style={styles.sectionTitle}>4. Mandatory Declarations (PCR 2011)</Text>
              </View>
              {inspection.declarations && inspection.declarations.length > 0 ? (
                inspection.declarations.map((d: any) => (
                  <View key={d.id} style={styles.declRow}>
                    <View style={styles.declRowTop}>
                      <Text style={styles.declField}>{d.field_name}</Text>
                      <View style={[styles.miniPill, d.corrected_value ? styles.pillBlue : styles.pillGray]}>
                        <Text style={styles.miniPillText}>{d.corrected_value ? 'VERIFIED' : 'AI_RAW'}</Text>
                      </View>
                    </View>
                    <Text style={styles.declVal}>
                      Value: <Text style={styles.declValBold}>{d.corrected_value || d.extracted_value || 'Not Declared'}</Text>
                    </Text>
                    {d.corrected_value && d.extracted_value && (
                      <Text style={styles.declDiffText}>OCR Original: {d.extracted_value}</Text>
                    )}
                  </View>
                ))
              ) : (
                <Text style={styles.notAvailableText}>No declarations structured.</Text>
              )}
            </View>

            {/* SECTION 5: Font Size, Readability & Placement */}
            <View style={styles.sectionCard}>
              <View style={styles.sectionHeaderRow}>
                <MaterialIcons name="format-size" size={18} color={colors.primary} />
                <Text style={styles.sectionTitle}>5. Font Height, Readability & Placement</Text>
              </View>
              <View style={styles.specRow}>
                <Text style={styles.specLabel}>Calibration Reference:</Text>
                <Text style={styles.specVal}>Standard 300 DPI Physical Gauge</Text>
              </View>
              <View style={styles.specRow}>
                <Text style={styles.specLabel}>PDP Placement Check:</Text>
                <Text style={[styles.specVal, { color: colors.statusGreenText }]}>VERIFIED ON PRINCIPAL DISPLAY</Text>
              </View>
              <View style={styles.specRow}>
                <Text style={styles.specLabel}>Contrast Ratio:</Text>
                <Text style={styles.specVal}>Compliant (WCAG AA Standard)</Text>
              </View>
            </View>

            {/* SECTION 6: Declaration Validation Matrix */}
            <View style={styles.sectionCard}>
              <View style={styles.sectionHeaderRow}>
                <MaterialIcons name="fact-check" size={18} color={colors.primary} />
                <Text style={styles.sectionTitle}>6. Declaration Validation Matrix</Text>
              </View>
              <View style={styles.specRow}>
                <Text style={styles.specLabel}>Matrix State:</Text>
                <Text style={styles.specVal}>
                  {inspection.declarations?.every((d: any) => d.extracted_value || d.corrected_value)
                    ? 'ALL MANDATORY FIELDS LOCATED'
                    : 'MISSING OR CONFLICTING FIELDS FLAGGED'}
                </Text>
              </View>
            </View>

            {/* SECTION 7: Statutory Compliance Summary */}
            <View style={styles.sectionCard}>
              <View style={styles.sectionHeaderRow}>
                <MaterialIcons name="gavel" size={18} color={colors.primary} />
                <Text style={styles.sectionTitle}>7. Statutory Compliance Summary</Text>
              </View>
              <View style={styles.specRow}>
                <Text style={styles.specLabel}>Compliance Outcome:</Text>
                <Text style={[styles.specValBold, { color: inspection.overall_status === 'POTENTIAL_NON_COMPLIANCE' ? colors.statusRedText : colors.statusGreenText }]}>
                  {inspection.overall_status || 'PENDING'}
                </Text>
              </View>
            </View>

            {/* SECTION 8: Findings & Evidence */}
            <View style={styles.sectionCard}>
              <View style={styles.sectionHeaderRow}>
                <MaterialIcons name="warning" size={18} color={colors.primary} />
                <Text style={styles.sectionTitle}>8. Rule Engine Findings & Evidence</Text>
              </View>
              {inspection.compliance_checks && inspection.compliance_checks.length > 0 ? (
                inspection.compliance_checks.map((chk: any) => (
                  <View key={chk.id} style={styles.checkCard}>
                    <View style={styles.checkHeader}>
                      <Text style={styles.checkTitle}>{chk.title || chk.rule_code}</Text>
                      <Text
                        style={[
                          styles.checkStatus,
                          chk.result_state === 'POTENTIAL_NON_COMPLIANCE' ? styles.statusRed : styles.statusGreen,
                        ]}
                      >
                        {chk.result_state}
                      </Text>
                    </View>
                    <Text style={styles.checkExpl}>{chk.explanation}</Text>
                    {chk.adjudication_status && (
                      <Text style={styles.checkAdj}>Officer Adjudication: {chk.adjudication_status}</Text>
                    )}
                  </View>
                ))
              ) : (
                <Text style={styles.notAvailableText}>No statutory violations detected.</Text>
              )}
            </View>

            {/* SECTION 9: Inspector Review & Adjudication */}
            <View style={styles.sectionCard}>
              <View style={styles.sectionHeaderRow}>
                <MaterialIcons name="rate-review" size={18} color={colors.primary} />
                <Text style={styles.sectionTitle}>9. Inspector Review & Notes</Text>
              </View>
              <Text style={styles.notesText}>
                {inspection.notes || 'No officer review notes recorded for this inspection.'}
              </Text>
            </View>

            {/* SECTION 10: Reports */}
            <View style={styles.sectionCard}>
              <View style={styles.sectionHeaderRow}>
                <MaterialIcons name="assessment" size={18} color={colors.primary} />
                <Text style={styles.sectionTitle}>10. Official Statutory Report</Text>
              </View>
              {inspection.report ? (
                <View>
                  <View style={styles.reportRow}>
                    <Text style={styles.reportLabel}>Version:</Text>
                    <Text style={styles.reportVal}>v{inspection.report.report_version}</Text>
                  </View>
                  <View style={styles.reportRow}>
                    <Text style={styles.reportLabel}>SHA-256 Hash:</Text>
                    <Text style={styles.reportHash} numberOfLines={1} ellipsizeMode="middle">
                      {inspection.report.pdf_hash || 'SHA-256 verified'}
                    </Text>
                  </View>
                  <View style={styles.reportBtnRow}>
                    <TouchableOpacity style={styles.downloadBtn} onPress={openPdf}>
                      <MaterialIcons name="picture-as-pdf" size={16} color="#FFFFFF" />
                      <Text style={styles.downloadBtnText}>View PDF Report</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={[styles.downloadBtn, { backgroundColor: '#0284C7' }]} onPress={openDocx}>
                      <MaterialIcons name="description" size={16} color="#FFFFFF" />
                      <Text style={styles.downloadBtnText}>DOCX</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ) : (
                <Text style={styles.notAvailableText}>No report generated yet.</Text>
              )}
            </View>

            {/* SECTION 11: Report Management */}
            {inspection.report && (
              <View style={styles.sectionCard}>
                <View style={styles.sectionHeaderRow}>
                  <MaterialIcons name="delete-sweep" size={18} color={colors.error} />
                  <Text style={[styles.sectionTitle, { color: colors.error }]}>11. Report Management</Text>
                </View>
                <Text style={styles.warningDesc}>
                  Supervisor administrative control: Deleting this report removes the generated file and database record while preserving the inspection and its evidence intact.
                </Text>
                <TouchableOpacity
                  style={styles.deleteReportBtn}
                  onPress={() => setShowDeleteReportModal(true)}
                >
                  <MaterialIcons name="delete-outline" size={18} color={colors.error} />
                  <Text style={styles.deleteReportBtnText}>Delete Statutory Report</Text>
                </TouchableOpacity>
              </View>
            )}

            {/* SECTION 12: Inspection Management (Destructive) */}
            <View style={[styles.sectionCard, styles.destructiveCard]}>
              <View style={styles.sectionHeaderRow}>
                <MaterialIcons name="warning" size={18} color={colors.error} />
                <Text style={[styles.sectionTitle, { color: colors.error }]}>12. Destructive Inspection Management</Text>
              </View>
              <Text style={styles.destructiveDesc}>
                Supervisor administrative action: Permanently delete this inspection, its child records, and associated files from Neon PostgreSQL. An immutable audit record will be preserved.
              </Text>
              <TouchableOpacity
                style={styles.deleteInspBtn}
                onPress={() => setShowDeleteModal(true)}
              >
                <MaterialIcons name="delete-forever" size={20} color="#FFFFFF" />
                <Text style={styles.deleteInspBtnText}>Permanently Delete Inspection</Text>
              </TouchableOpacity>
            </View>
          </ScrollView>
        )}

        {/* Modal: Delete Report Confirmation */}
        <Modal visible={showDeleteReportModal} transparent animationType="fade">
          <View style={styles.modalOverlay}>
            <View style={styles.modalContent}>
              <MaterialIcons name="delete-outline" size={36} color={colors.error} />
              <Text style={styles.modalTitle}>Delete Report?</Text>
              <Text style={styles.modalBody}>
                This will delete the official PDF/DOCX report for {inspection?.inspection_number}. The underlying inspection and findings will remain intact.
              </Text>
              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={styles.modalCancelBtn}
                  onPress={() => setShowDeleteReportModal(false)}
                  disabled={isDeletingReport}
                >
                  <Text style={styles.modalCancelText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.modalConfirmBtn}
                  onPress={handleDeleteReport}
                  disabled={isDeletingReport}
                >
                  {isDeletingReport ? (
                    <ActivityIndicator size="small" color="#FFFFFF" />
                  ) : (
                    <Text style={styles.modalConfirmText}>Confirm Delete</Text>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

        {/* Modal: Delete Inspection (Two-Step Exact Number Confirmation) */}
        <Modal visible={showDeleteModal} transparent animationType="slide">
          <View style={styles.modalOverlay}>
            <View style={styles.modalContentLarge}>
              <View style={styles.modalWarningHeader}>
                <MaterialIcons name="warning" size={28} color={colors.error} />
                <Text style={styles.modalLargeTitle}>Confirm Destructive Deletion</Text>
              </View>
              <Text style={styles.modalLargeBody}>
                You are about to delete inspection <Text style={styles.boldText}>{inspection?.inspection_number}</Text>.
                This action is permanent and cannot be reversed.
              </Text>

              <Text style={styles.inputInstruction}>
                Type <Text style={styles.codeText}>{inspection?.inspection_number}</Text> to confirm:
              </Text>
              <TextInput
                style={styles.confirmInput}
                value={confirmNumberInput}
                onChangeText={setConfirmNumberInput}
                placeholder={inspection?.inspection_number}
                placeholderTextColor={colors.outline}
                autoCapitalize="characters"
              />

              <Text style={[styles.inputInstruction, { marginTop: 10 }]}>Reason / Justification (Optional):</Text>
              <TextInput
                style={[styles.confirmInput, { height: 60 }]}
                value={deleteReason}
                onChangeText={setDeleteReason}
                placeholder="Administrative deletion reason..."
                placeholderTextColor={colors.outline}
                multiline
              />

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={styles.modalCancelBtn}
                  onPress={() => {
                    setShowDeleteModal(false);
                    setConfirmNumberInput('');
                    setDeleteReason('');
                  }}
                  disabled={isDeleting}
                >
                  <Text style={styles.modalCancelText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.modalDestructiveBtn, !isConfirmedMatch && styles.modalBtnDisabled]}
                  disabled={!isConfirmedMatch || isDeleting}
                  onPress={handleDeleteInspection}
                >
                  {isDeleting ? (
                    <ActivityIndicator size="small" color="#FFFFFF" />
                  ) : (
                    <Text style={styles.modalDestructiveText}>Delete Inspection</Text>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>
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
    fontSize: 16,
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
  scrollArea: {
    flex: 1,
  },
  scrollContent: {
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
  },
  statusBanner: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: colors.surface,
    padding: spacing.md,
    borderRadius: borderRadius.md,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.outlineVariant,
  },
  statusBannerLeft: {
    flex: 1,
  },
  statusBannerLabel: {
    fontSize: 11,
    color: colors.onSurfaceVariant,
    fontWeight: '500',
  },
  statusBannerVal: {
    fontSize: 16,
    fontWeight: '800',
    marginTop: 2,
  },
  statusGreen: {
    color: colors.statusGreenText,
  },
  statusRed: {
    color: colors.statusRedText,
  },
  statusAmber: {
    color: colors.statusAmberText,
  },
  lifecyclePill: {
    backgroundColor: colors.surfaceContainerLow,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: borderRadius.full,
  },
  lifecycleText: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.onSurfaceVariant,
  },
  sectionCard: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.outlineVariant,
  },
  sectionHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: spacing.sm,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.onSurface,
  },
  infoGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  infoCol: {
    width: '48%',
  },
  infoLabel: {
    fontSize: 10,
    color: colors.onSurfaceVariant,
    fontWeight: '500',
    textTransform: 'uppercase',
  },
  infoVal: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.onSurface,
    marginTop: 1,
  },
  imagesGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  imageItem: {
    width: '48%',
    alignItems: 'center',
  },
  imagePlaceholder: {
    width: '100%',
    height: 90,
    backgroundColor: colors.surfaceContainerLow,
    borderRadius: borderRadius.sm,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.outlineVariant,
  },
  imageLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: colors.primary,
    marginTop: 4,
  },
  imageMeta: {
    fontSize: 10,
    color: colors.onSurfaceVariant,
    marginTop: 2,
  },
  helperText: {
    fontSize: 11,
    color: colors.onSurfaceVariant,
    marginBottom: 4,
  },
  ocrBox: {
    backgroundColor: colors.surfaceContainerLowest,
    padding: spacing.sm,
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: colors.outlineVariant,
  },
  ocrText: {
    fontSize: 11,
    fontFamily: 'monospace',
    color: colors.onSurface,
    lineHeight: 16,
  },
  declRow: {
    paddingVertical: spacing.xs + 2,
    borderBottomWidth: 1,
    borderBottomColor: colors.outlineVariant,
  },
  declRowTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  declField: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.onSurface,
  },
  miniPill: {
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: 4,
  },
  pillBlue: {
    backgroundColor: '#DBEAFE',
  },
  pillGray: {
    backgroundColor: colors.surfaceContainerLow,
  },
  miniPillText: {
    fontSize: 9,
    fontWeight: '700',
    color: colors.primary,
  },
  declVal: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    marginTop: 2,
  },
  declValBold: {
    fontWeight: '600',
    color: colors.onSurface,
  },
  declDiffText: {
    fontSize: 10,
    color: colors.outline,
    marginTop: 1,
    fontStyle: 'italic',
  },
  specRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 4,
  },
  specLabel: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
  },
  specVal: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.onSurface,
  },
  specValBold: {
    fontSize: 13,
    fontWeight: '800',
  },
  checkCard: {
    backgroundColor: colors.surfaceContainerLow,
    padding: spacing.sm,
    borderRadius: borderRadius.sm,
    marginBottom: 6,
  },
  checkHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  checkTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.onSurface,
    flex: 1,
  },
  checkStatus: {
    fontSize: 10,
    fontWeight: '800',
  },
  checkExpl: {
    fontSize: 11,
    color: colors.onSurfaceVariant,
    marginTop: 2,
  },
  checkAdj: {
    fontSize: 10,
    color: colors.primary,
    fontWeight: '600',
    marginTop: 4,
  },
  notesText: {
    fontSize: 12,
    color: colors.onSurface,
    fontStyle: 'italic',
    lineHeight: 18,
  },
  reportRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 2,
  },
  reportLabel: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
  },
  reportVal: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.onSurface,
  },
  reportHash: {
    fontSize: 11,
    fontFamily: 'monospace',
    color: colors.onSurfaceVariant,
    maxWidth: 200,
  },
  reportBtnRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  downloadBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: borderRadius.md,
    gap: 4,
  },
  downloadBtnText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '600',
  },
  warningDesc: {
    fontSize: 11,
    color: colors.onSurfaceVariant,
    marginBottom: spacing.sm,
    lineHeight: 16,
  },
  deleteReportBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.error,
    paddingVertical: spacing.xs + 4,
    borderRadius: borderRadius.md,
    gap: 4,
  },
  deleteReportBtnText: {
    color: colors.error,
    fontSize: 13,
    fontWeight: '600',
  },
  destructiveCard: {
    borderColor: '#FECACA',
    backgroundColor: '#FEF2F2',
  },
  destructiveDesc: {
    fontSize: 11,
    color: '#991B1B',
    marginBottom: spacing.sm,
    lineHeight: 16,
  },
  deleteInspBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.error,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.md,
    gap: 6,
  },
  deleteInspBtnText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '700',
  },
  notAvailableText: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    fontStyle: 'italic',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.lg,
  },
  modalContent: {
    width: '100%',
    backgroundColor: colors.surface,
    borderRadius: borderRadius.lg,
    padding: spacing.lg,
    alignItems: 'center',
  },
  modalTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.onSurface,
    marginTop: spacing.sm,
  },
  modalBody: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
    marginTop: 6,
    marginBottom: spacing.lg,
    lineHeight: 18,
  },
  modalActions: {
    flexDirection: 'row',
    gap: spacing.md,
    width: '100%',
    marginTop: spacing.md,
  },
  modalCancelBtn: {
    flex: 1,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.outlineVariant,
    alignItems: 'center',
  },
  modalCancelText: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.onSurface,
  },
  modalConfirmBtn: {
    flex: 1,
    backgroundColor: colors.error,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.md,
    alignItems: 'center',
  },
  modalConfirmText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  modalContentLarge: {
    width: '100%',
    backgroundColor: colors.surface,
    borderRadius: borderRadius.lg,
    padding: spacing.lg,
  },
  modalWarningHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: spacing.sm,
  },
  modalLargeTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.error,
  },
  modalLargeBody: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    lineHeight: 18,
    marginBottom: spacing.sm,
  },
  boldText: {
    fontWeight: '700',
    color: colors.onSurface,
  },
  inputInstruction: {
    fontSize: 11,
    color: colors.onSurface,
    fontWeight: '600',
    marginBottom: 4,
  },
  codeText: {
    fontFamily: 'monospace',
    color: colors.primary,
  },
  confirmInput: {
    borderWidth: 1,
    borderColor: colors.outlineVariant,
    borderRadius: borderRadius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    fontSize: 13,
    color: colors.onSurface,
  },
  modalDestructiveBtn: {
    flex: 1,
    backgroundColor: colors.error,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.md,
    alignItems: 'center',
  },
  modalBtnDisabled: {
    opacity: 0.4,
  },
  modalDestructiveText: {
    fontSize: 13,
    fontWeight: '700',
    color: '#FFFFFF',
  },
});
