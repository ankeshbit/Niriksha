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
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { AppHeader } from '../components/AppHeader';
import { api } from '../services/api';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

const FIELD_LABELS: Record<string, string> = {
  commodity_name: 'Name of Commodity (Rule 6(1)(f))',
  manufacturer_details: 'Manufacturer / Packer (Rule 6(1)(a))',
  net_quantity: 'Net Quantity (Rule 6(1)(c))',
  mrp: 'Maximum Retail Price (MRP) (Rule 6(1)(e))',
  date_of_manufacture_packing: 'Month & Year of Mfg/Packing (Rule 6(1)(d))',
  consumer_care_details: 'Consumer Care Helpline (Rule 6(1)(g))',
  country_of_origin: 'Country of Origin (Rule 6(1)(b))',
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
      setDeclarations(data);
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

  return (
    <View style={styles.container}>
      <AppHeader
        title="EXTRACTED DECLARATIONS"
        subtitle={`Audit Review: ${inspectionNumber || 'Statutory Declarations'}`}
        showBack={true}
        onBackPress={() => navigation.goBack()}
      />

      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Instruction Card */}
        <View style={styles.infoCard}>
          <MaterialIcons name="fact-check" size={20} color={colors.primary} />
          <Text style={styles.infoText}>
            Review extracted statutory fields. Tap the edit icon to verify or correct any field before rule evaluation.
          </Text>
        </View>

        {loading ? (
          <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
        ) : (
          <View style={styles.tableCard}>
            {declarations.map((decl, idx) => {
              const isLast = idx === declarations.length - 1;
              const label = FIELD_LABELS[decl.field_name] || decl.field_name.toUpperCase();
              const displayVal = decl.effective_value || decl.extracted_value;
              const isCorrected = decl.verification_status === 'CORRECTED';

              return (
                <View key={decl.id} style={[styles.declRow, !isLast && styles.rowBorder]}>
                  <View style={styles.rowTopLine}>
                    <Text style={styles.fieldLabelText}>{label}</Text>
                    <TouchableOpacity
                      onPress={() => openEditModal(decl)}
                      style={styles.editIconButton}
                      hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                    >
                      <MaterialIcons name="edit" size={18} color={colors.primary} />
                    </TouchableOpacity>
                  </View>

                  <Text
                    style={[
                      styles.valueText,
                      !displayVal && styles.missingValueText,
                    ]}
                  >
                    {displayVal || 'Not Detected on Package'}
                  </Text>

                  {/* Badges Row */}
                  <View style={styles.badgesRow}>
                    <View style={styles.aiBadge}>
                      <MaterialIcons name="memory" size={12} color={colors.onSurfaceVariant} />
                      <Text style={styles.aiBadgeText}>OCR Extracted</Text>
                    </View>

                    {isCorrected ? (
                      <View style={styles.verifiedBadge}>
                        <Text style={styles.verifiedBadgeText}>Verified by Inspector</Text>
                      </View>
                    ) : decl.extraction_status === 'NOT_FOUND' ? (
                      <View style={styles.notFoundBadge}>
                        <Text style={styles.notFoundBadgeText}>Not Found</Text>
                      </View>
                    ) : decl.confidence >= 0.85 ? (
                      <View style={styles.highConfBadge}>
                        <Text style={styles.highConfBadgeText}>
                          OCR High ({Math.round(decl.confidence * 100)}%)
                        </Text>
                      </View>
                    ) : (
                      <View style={styles.lowConfBadge}>
                        <Text style={styles.lowConfBadgeText}>
                          Needs Verification ({Math.round(decl.confidence * 100)}%)
                        </Text>
                      </View>
                    )}
                  </View>
                </View>
              );
            })}
          </View>
        )}

        {/* Evaluate Button */}
        <TouchableOpacity
          style={styles.evalButton}
          onPress={handleEvaluateRules}
          disabled={evaluating || loading}
          activeOpacity={0.85}
        >
          {evaluating ? (
            <ActivityIndicator size="small" color={colors.onPrimary} />
          ) : (
            <View style={styles.buttonInner}>
              <Text style={styles.evalButtonText}>Evaluate Statutory Rules (PCR 2011)</Text>
              <MaterialIcons name="gavel" size={18} color={colors.onPrimary} />
            </View>
          )}
        </TouchableOpacity>
      </ScrollView>

      {/* In-Place Edit / Verification Modal */}
      <Modal visible={!!editingDecl} transparent animationType="fade">
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={typography.sectionHeader}>
                Verify / Correct Declaration
              </Text>
              <TouchableOpacity onPress={() => setEditingDecl(null)}>
                <MaterialIcons name="close" size={22} color={colors.onSurfaceVariant} />
              </TouchableOpacity>
            </View>

            <Text style={styles.modalFieldLabel}>
              {editingDecl ? FIELD_LABELS[editingDecl.field_name] : ''}
            </Text>

            <View style={styles.modalInputGroup}>
              <Text style={typography.labelCaps}>Verified Value</Text>
              <TextInput
                style={styles.modalTextInput}
                value={correctedValue}
                onChangeText={setCorrectedValue}
                placeholder="Enter verified label value"
                placeholderTextColor={colors.outline}
              />
            </View>

            <View style={styles.modalInputGroup}>
              <Text style={typography.labelCaps}>Officer Correction Reason</Text>
              <TextInput
                style={styles.modalTextInput}
                value={correctionReason}
                onChangeText={setCorrectionReason}
                placeholder="e.g. Verified on back panel text"
                placeholderTextColor={colors.outline}
              />
            </View>

            <View style={styles.modalActions}>
              <TouchableOpacity
                style={styles.modalCancelBtn}
                onPress={() => setEditingDecl(null)}
              >
                <Text style={styles.modalCancelText}>Cancel</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.modalSaveBtn}
                onPress={handleSaveCorrection}
                disabled={savingCorrection}
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
  infoCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.stackMd,
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    gap: 8,
  },
  infoText: {
    ...typography.caption,
    color: colors.onSurface,
    flex: 1,
  },
  tableCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    overflow: 'hidden',
  },
  declRow: {
    padding: spacing.marginX,
    gap: 4,
  },
  rowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  rowTopLine: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  fieldLabelText: {
    ...typography.labelCaps,
    color: colors.onSurfaceVariant,
    fontSize: 11,
    flex: 1,
  },
  editIconButton: {
    padding: 4,
  },
  valueText: {
    ...typography.bodyMdMedium,
    color: colors.onSurface,
    fontSize: 15,
  },
  missingValueText: {
    color: colors.secondary,
    fontStyle: 'italic',
  },
  badgesRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 2,
  },
  aiBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: borderRadius.sm,
    gap: 3,
  },
  aiBadgeText: {
    ...typography.caption,
    fontSize: 10,
    color: colors.onSurfaceVariant,
  },
  verifiedBadge: {
    backgroundColor: '#eff6ff',
    borderWidth: 1,
    borderColor: '#93c5fd',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: borderRadius.sm,
  },
  verifiedBadgeText: {
    ...typography.caption,
    fontSize: 10,
    color: '#1d4ed8',
    fontWeight: '700',
  },
  notFoundBadge: {
    backgroundColor: colors.surfaceContainerHigh,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: borderRadius.sm,
  },
  notFoundBadgeText: {
    ...typography.caption,
    fontSize: 10,
    color: colors.secondary,
  },
  highConfBadge: {
    backgroundColor: colors.statusGreenBg,
    borderWidth: 1,
    borderColor: colors.statusGreenText,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: borderRadius.sm,
  },
  highConfBadgeText: {
    ...typography.caption,
    fontSize: 10,
    color: colors.statusGreenText,
    fontWeight: '600',
  },
  lowConfBadge: {
    backgroundColor: colors.statusAmberBg,
    borderWidth: 1,
    borderColor: colors.statusAmberText,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: borderRadius.sm,
  },
  lowConfBadgeText: {
    ...typography.caption,
    fontSize: 10,
    color: colors.statusAmberText,
    fontWeight: '600',
  },
  evalButton: {
    backgroundColor: colors.primary,
    paddingVertical: 12,
    borderRadius: borderRadius.lg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  evalButtonText: {
    ...typography.sectionHeader,
    color: colors.onPrimary,
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
    padding: spacing.marginX,
    gap: spacing.stackMd,
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  modalFieldLabel: {
    ...typography.labelCaps,
    color: colors.primary,
    fontSize: 11,
  },
  modalInputGroup: {
    gap: 4,
  },
  modalTextInput: {
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
    marginTop: spacing.tight,
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
    paddingHorizontal: 14,
    borderRadius: borderRadius.lg,
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: 120,
  },
  modalSaveText: {
    ...typography.bodySm,
    fontWeight: '700',
    color: colors.onPrimary,
  },
});
