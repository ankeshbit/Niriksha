import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  Modal,
  TextInput,
  Alert,
  SafeAreaView,
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { BottomNav } from '../components/BottomNav';
import { ProfileAvatar } from '../components/ProfileAvatar';
import { api } from '../services/api';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

const FIELD_LABELS: Record<string, string> = {
  commodity_name: 'Product Name',
  manufacturer_details: 'Manufacturer',
  manufacturer_address: 'Address',
  net_quantity: 'Net Quantity',
  mrp: 'MRP',
  date_of_manufacture_packing: 'Date of Packing',
  consumer_care_details: 'Consumer Care Information',
  country_of_origin: 'Country of Origin',
};

export const ExtractedDeclarationsScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'ExtractedDeclarations'>>();
  const { inspectionId, inspectionNumber } = route.params;

  const [declarations, setDeclarations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);

  // Edit Modal State
  const [editingDecl, setEditingDecl] = useState<any | null>(null);
  const [correctedValue, setCorrectedValue] = useState('');
  const [correctionReason, setCorrectionReason] = useState('');
  const [savingCorrection, setSavingCorrection] = useState(false);

  const loadDeclarations = async () => {
    try {
      const data = await api.getDeclarations(inspectionId);
      setDeclarations(data || []);
    } catch (err) {
      console.error('Failed to load declarations:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDeclarations();
  }, [inspectionId]);

  const openEditModal = (decl: any) => {
    setEditingDecl(decl);
    setCorrectedValue(decl.effective_value || decl.extracted_value || '');
    setCorrectionReason(decl.correction_reason || 'Verified on physical package label');
  };

  const handleSaveCorrection = async () => {
    if (!editingDecl) return;

    setSavingCorrection(true);
    try {
      await api.updateDeclaration(editingDecl.id, {
        corrected_value: correctedValue.trim(),
        verification_status: 'CORRECTED',
        correction_reason: correctionReason.trim() || undefined,
      });

      await loadDeclarations();
      setEditingDecl(null);
    } catch (err: any) {
      Alert.alert('Update Failed', err.message || 'Could not update declaration.');
    } finally {
      setSavingCorrection(false);
    }
  };

  const handleEvaluateRules = async () => {
    setEvaluating(true);
    try {
      await api.evaluateRules(inspectionId);
      navigation.navigate('Findings', {
        inspectionId,
        inspectionNumber,
      });
    } catch (err: any) {
      Alert.alert('Evaluation Failed', err.message || 'Rule evaluation failed.');
    } finally {
      setEvaluating(false);
    }
  };

  const todayStr = new Date().toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        {/* Stitch TopAppBar Header */}
        <View style={styles.topHeader}>
          <View style={styles.headerLeft}>
            <TouchableOpacity
              style={styles.backButton}
              onPress={() => navigation.goBack()}
              activeOpacity={0.7}
            >
              <MaterialIcons name="arrow-back" size={24} color={colors.primary} />
            </TouchableOpacity>
            <View>
              <Text style={styles.headerTitle}>Legal Metrology</Text>
              <Text style={styles.headerSubtitle}>
                ID: {inspectionNumber || 'LM-2026-00891'} • {todayStr}
              </Text>
            </View>
          </View>
          <ProfileAvatar size={36} />
        </View>

        <ScrollView
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Header Section */}
          <View style={styles.sectionHeaderBox}>
            <Text style={styles.sectionHeaderTitle}>Extracted Declarations Review</Text>
            <Text style={styles.sectionHeaderSubtitle}>
              Review and verify the data extracted via AI/OCR.
            </Text>
          </View>

          {loading ? (
            <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
          ) : (
            <View style={styles.tableContainer}>
              {declarations.map((decl, idx) => {
                const label = FIELD_LABELS[decl.field_type] || decl.field_type.replace(/_/g, ' ');
                const isConflict = decl.ocr_confidence === 'CONFLICT' || decl.has_conflict;
                const isNotFound =
                  !decl.extracted_value && (!decl.effective_value || decl.effective_value === 'NOT_FOUND');
                const isLast = idx === declarations.length - 1;

                return (
                  <View
                    key={decl.id || idx}
                    style={[
                      styles.tableRow,
                      isConflict && styles.rowConflict,
                      isNotFound && styles.rowNotFound,
                      !isLast && styles.rowBorder,
                    ]}
                  >
                    <View style={styles.rowTop}>
                      <Text
                        style={[
                          styles.fieldLabelCaps,
                          isConflict && styles.textRed,
                          isNotFound && styles.textAmber,
                        ]}
                      >
                        {label}
                      </Text>
                      <TouchableOpacity
                        style={styles.editBtn}
                        onPress={() => openEditModal(decl)}
                        activeOpacity={0.7}
                      >
                        <MaterialIcons name="edit" size={18} color={colors.primary} />
                      </TouchableOpacity>
                    </View>

                    {isConflict ? (
                      <View style={styles.conflictContent}>
                        <View style={styles.alertHeaderRow}>
                          <MaterialIcons name="warning" size={18} color={colors.statusRedText} />
                          <Text style={styles.conflictTitle}>CONFLICT DETECTED</Text>
                        </View>
                        <Text style={styles.conflictValues}>
                          {decl.effective_value || decl.extracted_value || 'Multiple values detected across panels'}
                        </Text>
                        <Text style={styles.conflictHelper}>
                          Two different values found across images. Manual verification required.
                        </Text>
                      </View>
                    ) : isNotFound ? (
                      <View style={styles.notFoundContent}>
                        <View style={styles.alertHeaderRow}>
                          <MaterialIcons name="error" size={18} color={colors.statusAmberText} />
                          <Text style={styles.notFoundTitle}>Field Not Found</Text>
                        </View>
                        <Text style={styles.notFoundSubtext}>OCR could not detect this field.</Text>
                        <TouchableOpacity
                          style={styles.manualEntryBtn}
                          onPress={() => openEditModal(decl)}
                          activeOpacity={0.7}
                        >
                          <Text style={styles.manualEntryText}>[ Enter Value Manually ]</Text>
                        </TouchableOpacity>
                      </View>
                    ) : (
                      <View style={styles.valueRow}>
                        <Text style={styles.valueText}>
                          {decl.effective_value || decl.extracted_value || 'Not specified'}
                        </Text>
                      </View>
                    )}

                    {/* Chips Row */}
                    <View style={styles.chipsRow}>
                      <View style={styles.sourceChip}>
                        <MaterialIcons name="memory" size={14} color={colors.onSurfaceVariant} />
                        <Text style={styles.sourceChipText}>
                          {decl.verification_status === 'CORRECTED' ? 'Inspector Corrected' : 'AI/OCR Extracted'}
                        </Text>
                      </View>

                      {isConflict ? (
                        <View style={styles.conflictChip}>
                          <Text style={styles.conflictChipText}>CONFLICT — NEEDS MANUAL VERIFICATION</Text>
                        </View>
                      ) : isNotFound ? (
                        <View style={styles.notFoundChip}>
                          <Text style={styles.notFoundChipText}>OCR Result: not_found</Text>
                        </View>
                      ) : (
                        <View style={styles.goodChip}>
                          <Text style={styles.goodChipText}>
                            OCR Confidence: {decl.ocr_confidence || 'High'}
                          </Text>
                        </View>
                      )}
                    </View>
                  </View>
                );
              })}
            </View>
          )}

          {/* Action Button: Check for Potential Violations */}
          <TouchableOpacity
            style={styles.evaluateButton}
            onPress={handleEvaluateRules}
            disabled={evaluating}
            activeOpacity={0.85}
          >
            {evaluating ? (
              <ActivityIndicator size="small" color={colors.onPrimary} />
            ) : (
              <View style={styles.btnInner}>
                <MaterialIcons name="rule" size={20} color={colors.onPrimary} />
                <Text style={styles.evaluateButtonText}>Check for Potential Violations</Text>
              </View>
            )}
          </TouchableOpacity>

          <View style={styles.footerNote}>
            <Text style={styles.footerNoteText}>Smart India Hackathon 2026 Prototype</Text>
          </View>
        </ScrollView>

        {/* Edit Modal */}
        <Modal visible={!!editingDecl} transparent animationType="fade">
          <View style={styles.modalOverlay}>
            <View style={styles.modalContent}>
              <View style={styles.modalHeader}>
                <Text style={typography.sectionHeader}>
                  Edit {editingDecl ? FIELD_LABELS[editingDecl.field_type] || editingDecl.field_type : 'Declaration'}
                </Text>
                <TouchableOpacity onPress={() => setEditingDecl(null)}>
                  <MaterialIcons name="close" size={22} color={colors.onSurfaceVariant} />
                </TouchableOpacity>
              </View>

              <View style={styles.modalBody}>
                <Text style={typography.labelCaps}>Corrected / Verified Value</Text>
                <TextInput
                  style={styles.modalInput}
                  value={correctedValue}
                  onChangeText={setCorrectedValue}
                  placeholder="Enter correct value from package"
                  placeholderTextColor={colors.outline}
                />

                <Text style={[typography.labelCaps, { marginTop: 12 }]}>Reason for Modification</Text>
                <TextInput
                  style={styles.modalInput}
                  value={correctionReason}
                  onChangeText={setCorrectionReason}
                  placeholder="e.g. Verified on physical package label"
                  placeholderTextColor={colors.outline}
                />
              </View>

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={styles.modalCancelBtn}
                  onPress={() => setEditingDecl(null)}
                  disabled={savingCorrection}
                >
                  <Text style={styles.modalCancelText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.modalSaveBtn}
                  onPress={handleSaveCorrection}
                  disabled={savingCorrection}
                  activeOpacity={0.85}
                >
                  {savingCorrection ? (
                    <ActivityIndicator size="small" color={colors.onPrimary} />
                  ) : (
                    <Text style={styles.modalSaveText}>Save Correction</Text>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          </View>
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
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
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
  headerSubtitle: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
  },
  avatarCircle: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.surfaceContainerHigh,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarInitials: {
    ...typography.labelCaps,
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
  scrollContent: {
    paddingHorizontal: spacing.gutter,
    paddingTop: spacing.stackMd,
    paddingBottom: 90,
    gap: spacing.stackMd,
  },
  sectionHeaderBox: {
    gap: 2,
    marginBottom: 4,
  },
  sectionHeaderTitle: {
    ...typography.sectionHeader,
    fontSize: 16,
    lineHeight: 24,
    fontWeight: '600',
    color: colors.primary,
  },
  sectionHeaderSubtitle: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.onSurfaceVariant,
  },
  tableContainer: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    overflow: 'hidden',
  },
  tableRow: {
    padding: spacing.gutter,
    gap: 8,
  },
  rowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  rowConflict: {
    backgroundColor: colors.statusRedBg,
    borderColor: 'rgba(183, 28, 28, 0.2)',
  },
  rowNotFound: {
    backgroundColor: colors.statusAmberBg,
    borderColor: 'rgba(230, 81, 0, 0.2)',
  },
  rowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  fieldLabelCaps: {
    ...typography.labelCaps,
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 0.5,
    fontWeight: '600',
    color: colors.onSurfaceVariant,
    textTransform: 'uppercase',
  },
  textRed: {
    color: colors.statusRedText,
  },
  textAmber: {
    color: colors.statusAmberText,
  },
  editBtn: {
    padding: 4,
    borderRadius: borderRadius.DEFAULT,
  },
  valueRow: {
    marginBottom: 2,
  },
  valueText: {
    ...typography.bodyMd,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '600',
    color: colors.onSurface,
  },
  conflictContent: {
    gap: 4,
    marginBottom: 4,
  },
  alertHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  conflictTitle: {
    ...typography.bodyMd,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
    color: colors.statusRedText,
  },
  conflictValues: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.onSurface,
    marginLeft: 24,
  },
  conflictHelper: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
    marginLeft: 24,
  },
  notFoundContent: {
    gap: 4,
    marginBottom: 4,
  },
  notFoundTitle: {
    ...typography.bodyMd,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
    color: colors.statusAmberText,
  },
  notFoundSubtext: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.onSurface,
    marginLeft: 24,
  },
  manualEntryBtn: {
    marginLeft: 24,
    marginTop: 2,
  },
  manualEntryText: {
    ...typography.bodySm,
    fontSize: 13,
    fontWeight: '600',
    color: colors.primary,
    textDecorationLine: 'underline',
  },
  chipsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 8,
    marginTop: 2,
  },
  sourceChip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    paddingHorizontal: 8,
    paddingVertical: 2,
    gap: 4,
  },
  sourceChipText: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
  goodChip: {
    backgroundColor: colors.statusGreenBg,
    borderWidth: 1,
    borderColor: 'rgba(27, 94, 32, 0.2)',
    borderRadius: borderRadius.DEFAULT,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  goodChipText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.statusGreenText,
  },
  conflictChip: {
    backgroundColor: colors.statusRedBg,
    borderWidth: 1,
    borderColor: 'rgba(183, 28, 28, 0.2)',
    borderRadius: borderRadius.DEFAULT,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  conflictChipText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.statusRedText,
  },
  notFoundChip: {
    backgroundColor: colors.statusAmberBg,
    borderWidth: 1,
    borderColor: 'rgba(230, 81, 0, 0.2)',
    borderRadius: borderRadius.DEFAULT,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  notFoundChipText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.statusAmberText,
  },
  evaluateButton: {
    backgroundColor: colors.primary,
    paddingVertical: 14,
    borderRadius: borderRadius.xl,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 8,
  },
  btnInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  evaluateButtonText: {
    ...typography.sectionHeader,
    fontSize: 15,
    lineHeight: 22,
    color: colors.onPrimary,
    fontWeight: '600',
  },
  footerNote: {
    alignItems: 'center',
    marginTop: 8,
    marginBottom: 8,
  },
  footerNoteText: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.gutter,
  },
  modalContent: {
    width: '100%',
    maxWidth: 400,
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    padding: spacing.marginX,
    gap: spacing.stackMd,
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    paddingBottom: spacing.stackSm,
  },
  modalBody: {
    gap: 6,
  },
  modalInput: {
    backgroundColor: colors.surfaceBright,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    paddingHorizontal: 12,
    paddingVertical: 8,
    ...typography.bodyMd,
    color: colors.onSurface,
  },
  modalActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 8,
    marginTop: 8,
  },
  modalCancelBtn: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  modalCancelText: {
    ...typography.bodySm,
    fontWeight: '600',
    color: colors.secondary,
  },
  modalSaveBtn: {
    backgroundColor: colors.primary,
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: borderRadius.lg,
  },
  modalSaveText: {
    ...typography.bodySm,
    fontWeight: '700',
    color: colors.onPrimary,
  },
});
