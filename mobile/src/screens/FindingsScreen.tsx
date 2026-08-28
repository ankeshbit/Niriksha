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

type AdjudicationAction = 'CONFIRMED' | 'DISMISSED' | 'NOT_APPLICABLE' | 'CORRECTED';

export const FindingsScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'Findings'>>();
  const { inspectionId, inspectionNumber } = route.params;

  const [findings, setFindings] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Adjudication Modal state
  const [adjudicatingFinding, setAdjudicatingFinding] = useState<any | null>(null);
  const [actionType, setActionType] = useState<AdjudicationAction>('CONFIRMED');
  const [adjudicationNotes, setAdjudicationNotes] = useState('');
  const [correctedValue, setCorrectedValue] = useState('');
  const [savingAction, setSavingAction] = useState(false);

  const loadFindings = async () => {
    try {
      let data = await api.getFindings(inspectionId);
      if (!data || data.length === 0) {
        const evalRes = await api.evaluateRules(inspectionId);
        data = evalRes.findings;
      }
      setFindings(data);
    } catch (err) {
      console.error('Failed to load findings:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFindings();
  }, [inspectionId]);

  const openModal = (finding: any, action: AdjudicationAction) => {
    setAdjudicatingFinding(finding);
    setActionType(action);
    setCorrectedValue('');
    const defaultNotes: Record<AdjudicationAction, string> = {
      CONFIRMED: finding.adjudication_notes || 'Confirmed non-compliance on physical inspection.',
      DISMISSED: finding.adjudication_notes || 'Dismissed: Verified statutory exemption applies.',
      NOT_APPLICABLE: finding.adjudication_notes || 'Rule is not applicable to this commodity category.',
      CORRECTED: '',
    };
    setAdjudicationNotes(defaultNotes[action]);
  };

  const handleRequestNewImage = async (finding: any) => {
    Alert.alert(
      'Request New Image',
      `This will mark finding "${finding.title}" as needing more evidence and navigate you to capture a new package image. The existing finding record is preserved.\n\nProceed?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Capture New Image',
          onPress: async () => {
            try {
              await api.requestNewImage(finding.id);
              // Navigate to CaptureImages; after upload they return to Analyzing → Findings
              navigation.navigate('CaptureImages', { inspectionId, inspectionNumber });
            } catch (err: any) {
              Alert.alert('Error', err.message || 'Could not initiate new image request.');
            }
          },
        },
      ]
    );
  };

  const handleSaveAdjudication = async () => {
    if (!adjudicatingFinding) return;
    if (!adjudicationNotes.trim() && actionType !== 'CORRECTED') {
      Alert.alert('Required Note', 'Please provide a statutory justification note.');
      return;
    }
    if (actionType === 'CORRECTED' && !correctedValue.trim()) {
      Alert.alert('Required Value', 'Please enter the correct value for this declaration field.');
      return;
    }

    setSavingAction(true);
    try {
      await api.adjudicateFinding(adjudicatingFinding.id, {
        action: actionType,
        notes: adjudicationNotes.trim() || undefined,
        corrected_value: actionType === 'CORRECTED' ? correctedValue.trim() : undefined,
      });
      await loadFindings();
      setAdjudicatingFinding(null);
    } catch (err: any) {
      Alert.alert('Action Failed', err.message || 'Could not record inspector action.');
    } finally {
      setSavingAction(false);
    }
  };

  const getModalTitle = (): string => {
    switch (actionType) {
      case 'CONFIRMED': return 'Confirm Potential Violation';
      case 'DISMISSED': return 'Dismiss Finding';
      case 'NOT_APPLICABLE': return 'Mark as Not Applicable';
      case 'CORRECTED': return 'Provide Corrected Value';
    }
  };

  const getSubmitLabel = (): string => {
    switch (actionType) {
      case 'CONFIRMED': return 'Confirm Violation';
      case 'DISMISSED': return 'Dismiss Finding';
      case 'NOT_APPLICABLE': return 'Mark N/A';
      case 'CORRECTED': return 'Save Correction';
    }
  };

  const getSubmitBtnStyle = () => {
    switch (actionType) {
      case 'CONFIRMED': return styles.btnRed;
      case 'DISMISSED': return styles.btnGreen;
      case 'NOT_APPLICABLE': return styles.btnGrey;
      case 'CORRECTED': return styles.btnBlue;
    }
  };

  const renderAdjudicationBadge = (finding: any) => {
    const status = finding.adjudication_status;
    if (status === 'CONFIRMED') {
      return (
        <View style={styles.adjConfirmedBadge}>
          <MaterialIcons name="check" size={14} color={colors.statusRedText} />
          <Text style={styles.adjConfirmedText}>
            Confirmed by Inspector — {finding.adjudication_notes || 'Confirmed'}
          </Text>
        </View>
      );
    }
    if (status === 'DISMISSED') {
      return (
        <View style={styles.adjDismissedBadge}>
          <MaterialIcons name="close" size={14} color={colors.statusGreenText} />
          <Text style={styles.adjDismissedText}>
            Dismissed — {finding.adjudication_notes || 'Dismissed'}
          </Text>
        </View>
      );
    }
    if (status === 'NOT_APPLICABLE') {
      return (
        <View style={styles.adjNaBadge}>
          <MaterialIcons name="block" size={14} color={colors.onSurfaceVariant} />
          <Text style={styles.adjNaText}>
            Not Applicable — {finding.adjudication_notes || 'N/A'}
          </Text>
        </View>
      );
    }
    if (status === 'CORRECTED') {
      return (
        <View style={styles.adjCorrectedBadge}>
          <MaterialIcons name="edit" size={14} color={colors.primary} />
          <Text style={styles.adjCorrectedText}>
            Inspector Corrected — {finding.adjudication_notes || 'Value corrected'}
          </Text>
        </View>
      );
    }
    if (status === 'NEEDS_MORE_EVIDENCE') {
      return (
        <View style={styles.adjNeedsBadge}>
          <MaterialIcons name="camera-alt" size={14} color={colors.statusAmberText} />
          <Text style={styles.adjNeedsText}>
            Awaiting New Image — Evidence requested
          </Text>
        </View>
      );
    }
    return null;
  };

  // A finding is "resolved" if it has been adjudicated with a terminal action
  const resolvedActions = new Set(['CONFIRMED', 'DISMISSED', 'NOT_APPLICABLE', 'CORRECTED']);
  const unresolvedCount = findings.filter(
    (f) => f.result_state !== 'PASS' && !resolvedActions.has(f.adjudication_status)
  ).length;

  return (
    <View style={styles.container}>
      <AppHeader
        title="FINDINGS & RULES"
        subtitle={`Adjudication: ${inspectionNumber || 'Statutory Compliance'}`}
        showBack={true}
        onBackPress={() => navigation.goBack()}
      />

      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Info Banner */}
        <View style={styles.infoCard}>
          <MaterialIcons name="gavel" size={20} color={colors.primary} />
          <Text style={styles.infoText}>
            Deterministic PCR 2011 rule evaluation results. Each finding must be adjudicated before the final report can be generated.
          </Text>
        </View>

        {/* Unresolved warning */}
        {unresolvedCount > 0 && (
          <View style={styles.unresolvedBanner}>
            <MaterialIcons name="warning" size={16} color={colors.statusAmberText} />
            <Text style={styles.unresolvedText}>
              {unresolvedCount} finding{unresolvedCount > 1 ? 's' : ''} still require adjudication before finalizing.
            </Text>
          </View>
        )}

        {loading ? (
          <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
        ) : !findings || findings.length === 0 ? (
          <View style={styles.emptyCard}>
            <Text style={typography.bodySm}>No statutory rule evaluations recorded.</Text>
          </View>
        ) : (
          findings.map((finding) => {
            const isNonComp = finding.result_state === 'POTENTIAL_NON_COMPLIANCE';
            const isPass = finding.result_state === 'PASS';
            const isInsufficient = finding.result_state === 'INSUFFICIENT_EVIDENCE';
            const isResolved = resolvedActions.has(finding.adjudication_status);

            let cardBorder = colors.borderSubtle;
            let resultBadgeBg = colors.surfaceContainerLow;
            let resultBadgeText = colors.secondary;
            let resultLabel = 'NOT APPLICABLE';

            if (isNonComp) {
              cardBorder = colors.statusRedText;
              resultBadgeBg = colors.statusRedBg;
              resultBadgeText = colors.statusRedText;
              resultLabel = 'POTENTIAL NON-COMPLIANCE';
            } else if (isPass) {
              cardBorder = colors.statusGreenText;
              resultBadgeBg = colors.statusGreenBg;
              resultBadgeText = colors.statusGreenText;
              resultLabel = 'PASS';
            } else if (isInsufficient) {
              cardBorder = colors.statusAmberText;
              resultBadgeBg = colors.statusAmberBg;
              resultBadgeText = colors.statusAmberText;
              resultLabel = 'INSUFFICIENT EVIDENCE';
            }

            return (
              <View
                key={finding.id}
                style={[
                  styles.findingCard,
                  { borderColor: cardBorder },
                  isNonComp && !isResolved && styles.nonCompGlow,
                ]}
              >
                {/* Header: rule code + version + result badge */}
                <View style={styles.findingTopRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.ruleCodeText}>{finding.rule_code}</Text>
                    <Text style={styles.ruleTitleText}>{finding.title}</Text>
                    {/* Rule version + statutory reference */}
                    {finding.statutory_reference ? (
                      <Text style={styles.statutoryRefText}>
                        {finding.statutory_reference}
                        {finding.rule_version_number ? `  •  v${finding.rule_version_number}` : ''}
                      </Text>
                    ) : null}
                  </View>
                  <View style={[styles.resultBadge, { backgroundColor: resultBadgeBg, borderColor: resultBadgeText }]}>
                    <Text style={[styles.resultBadgeText, { color: resultBadgeText }]}>
                      {resultLabel}
                    </Text>
                  </View>
                </View>

                {/* Explanation */}
                <Text style={styles.explanationText}>{finding.explanation}</Text>

                {/* Effective Value & Evidence Link */}
                <View style={styles.evidenceBox}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.evaluatedLabel}>EVALUATED VALUE</Text>
                    <Text style={styles.evaluatedValue}>
                      {finding.extracted_value || 'None / Not Detected'}
                    </Text>
                  </View>
                  <TouchableOpacity
                    style={styles.evidenceLink}
                    onPress={() =>
                      navigation.navigate('EvidenceReview', {
                        inspectionId,
                        findingId: finding.id,
                      })
                    }
                    activeOpacity={0.7}
                  >
                    <MaterialIcons name="visibility" size={16} color={colors.primary} />
                    <Text style={styles.evidenceLinkText}>Evidence</Text>
                  </TouchableOpacity>
                </View>

                {/* Adjudication Status Badge */}
                {renderAdjudicationBadge(finding)}

                {/* Action Buttons — only for non-PASS findings */}
                {!isPass && (
                  <View style={styles.actionButtonsContainer}>
                    <View style={styles.actionButtonsRow}>
                      <TouchableOpacity
                        style={styles.dismissButton}
                        onPress={() => openModal(finding, 'DISMISSED')}
                        activeOpacity={0.8}
                      >
                        <MaterialIcons name="close" size={13} color={colors.secondary} />
                        <Text style={styles.dismissButtonText}>Dismiss</Text>
                      </TouchableOpacity>

                      <TouchableOpacity
                        style={styles.naButton}
                        onPress={() => openModal(finding, 'NOT_APPLICABLE')}
                        activeOpacity={0.8}
                      >
                        <MaterialIcons name="block" size={13} color={colors.onSurfaceVariant} />
                        <Text style={styles.naButtonText}>N/A</Text>
                      </TouchableOpacity>

                      <TouchableOpacity
                        style={styles.correctButton}
                        onPress={() => openModal(finding, 'CORRECTED')}
                        activeOpacity={0.8}
                      >
                        <MaterialIcons name="edit" size={13} color={colors.primary} />
                        <Text style={styles.correctButtonText}>Correct</Text>
                      </TouchableOpacity>
                    </View>

                    <View style={styles.actionButtonsRow}>
                      <TouchableOpacity
                        style={styles.requestImageButton}
                        onPress={() => handleRequestNewImage(finding)}
                        activeOpacity={0.8}
                      >
                        <MaterialIcons name="camera-alt" size={13} color={colors.statusAmberText} />
                        <Text style={styles.requestImageButtonText}>Request New Image</Text>
                      </TouchableOpacity>

                      <TouchableOpacity
                        style={styles.confirmButton}
                        onPress={() => openModal(finding, 'CONFIRMED')}
                        activeOpacity={0.8}
                      >
                        <MaterialIcons name="check" size={13} color={colors.onPrimary} />
                        <Text style={styles.confirmButtonText}>Confirm</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                )}
              </View>
            );
          })
        )}

        {/* Continue to Final Review Button */}
        <TouchableOpacity
          style={[
            styles.continueButton,
            unresolvedCount > 0 && styles.continueButtonDisabled,
          ]}
          onPress={() => {
            if (unresolvedCount > 0) {
              Alert.alert(
                'Unresolved Findings',
                `${unresolvedCount} finding${unresolvedCount > 1 ? 's' : ''} must be adjudicated (Confirm / Dismiss / Correct / N/A) before proceeding.`
              );
              return;
            }
            navigation.navigate('ReviewAndSubmit', { inspectionId, inspectionNumber });
          }}
          activeOpacity={0.85}
        >
          <Text style={styles.continueButtonText}>
            {unresolvedCount > 0
              ? `${unresolvedCount} Finding${unresolvedCount > 1 ? 's' : ''} Need Adjudication`
              : 'Continue to Final Summary'}
          </Text>
          <MaterialIcons name="arrow-forward" size={18} color={colors.onPrimary} style={{ marginLeft: 6 }} />
        </TouchableOpacity>
      </ScrollView>

      {/* Adjudication Modal */}
      <Modal visible={!!adjudicatingFinding} transparent animationType="fade">
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={typography.sectionHeader}>{getModalTitle()}</Text>
              <TouchableOpacity onPress={() => setAdjudicatingFinding(null)}>
                <MaterialIcons name="close" size={22} color={colors.onSurfaceVariant} />
              </TouchableOpacity>
            </View>

            <Text style={styles.modalSub}>
              {adjudicatingFinding?.rule_code}: {adjudicatingFinding?.title}
            </Text>

            {adjudicatingFinding?.statutory_reference ? (
              <Text style={styles.modalStatutory}>{adjudicatingFinding.statutory_reference}</Text>
            ) : null}

            {/* For CORRECTED action: show corrected value input */}
            {actionType === 'CORRECTED' && (
              <View style={styles.modalInputGroup}>
                <Text style={typography.labelCaps}>Correct Declaration Value</Text>
                <TextInput
                  style={styles.modalTextInput}
                  value={correctedValue}
                  onChangeText={setCorrectedValue}
                  placeholder="Enter the correct value found on package..."
                  placeholderTextColor={colors.outline}
                />
              </View>
            )}

            <View style={styles.modalInputGroup}>
              <Text style={typography.labelCaps}>
                {actionType === 'CONFIRMED'
                  ? 'Officer Confirmation Remarks'
                  : actionType === 'CORRECTED'
                  ? 'Reason for Correction (Optional)'
                  : 'Statutory Justification / Reason'}
              </Text>
              <TextInput
                style={[styles.modalTextInput, styles.modalTextArea]}
                value={adjudicationNotes}
                onChangeText={setAdjudicationNotes}
                placeholder={
                  actionType === 'CORRECTED'
                    ? 'Optional: reason for correction...'
                    : 'Enter justification remarks...'
                }
                placeholderTextColor={colors.outline}
                multiline
                numberOfLines={3}
              />
            </View>

            <View style={styles.modalActions}>
              <TouchableOpacity
                style={styles.modalCancelBtn}
                onPress={() => setAdjudicatingFinding(null)}
              >
                <Text style={styles.modalCancelText}>Cancel</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.modalConfirmBtn, getSubmitBtnStyle()]}
                onPress={handleSaveAdjudication}
                disabled={savingAction}
              >
                {savingAction ? (
                  <ActivityIndicator size="small" color={colors.onPrimary} />
                ) : (
                  <Text style={styles.modalConfirmText}>{getSubmitLabel()}</Text>
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
  unresolvedBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    padding: 10,
    backgroundColor: colors.statusAmberBg,
    borderWidth: 1,
    borderColor: colors.statusAmberText,
    borderRadius: borderRadius.lg,
  },
  unresolvedText: {
    ...typography.caption,
    fontWeight: '700',
    color: colors.statusAmberText,
    flex: 1,
  },
  emptyCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.stackLg,
    alignItems: 'center',
  },
  findingCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderRadius: borderRadius.lg,
    padding: spacing.marginX,
    gap: spacing.stackSm,
  },
  nonCompGlow: {
    backgroundColor: '#fffdfd',
  },
  findingTopRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 8,
  },
  ruleCodeText: {
    ...typography.labelCaps,
    color: colors.secondary,
    fontSize: 10,
  },
  ruleTitleText: {
    ...typography.sectionHeader,
    color: colors.primary,
    fontSize: 15,
    marginTop: 2,
  },
  statutoryRefText: {
    ...typography.caption,
    fontSize: 10,
    color: colors.onSurfaceVariant,
    marginTop: 2,
    fontStyle: 'italic',
  },
  resultBadge: {
    borderWidth: 1,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: borderRadius.sm,
  },
  resultBadgeText: {
    ...typography.caption,
    fontSize: 10,
    fontWeight: '700',
  },
  explanationText: {
    ...typography.bodySm,
    color: colors.onSurface,
    lineHeight: 18,
  },
  evidenceBox: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: 8,
    gap: 8,
  },
  evaluatedLabel: {
    ...typography.labelCaps,
    fontSize: 9,
    color: colors.onSurfaceVariant,
  },
  evaluatedValue: {
    ...typography.bodySm,
    fontWeight: '600',
    color: colors.primary,
  },
  evidenceLink: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 4,
    paddingHorizontal: 8,
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.sm,
    gap: 4,
  },
  evidenceLinkText: {
    ...typography.caption,
    fontWeight: '700',
    color: colors.primary,
  },
  adjConfirmedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.statusRedBg,
    padding: 6,
    borderRadius: borderRadius.sm,
    gap: 4,
  },
  adjConfirmedText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.statusRedText,
    flex: 1,
  },
  adjDismissedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.statusGreenBg,
    padding: 6,
    borderRadius: borderRadius.sm,
    gap: 4,
  },
  adjDismissedText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.statusGreenText,
    flex: 1,
  },
  adjNaBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    padding: 6,
    borderRadius: borderRadius.sm,
    gap: 4,
  },
  adjNaText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.onSurfaceVariant,
    flex: 1,
  },
  adjCorrectedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#e8f0fe',
    borderWidth: 1,
    borderColor: colors.primary,
    padding: 6,
    borderRadius: borderRadius.sm,
    gap: 4,
  },
  adjCorrectedText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.primary,
    flex: 1,
  },
  adjNeedsBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.statusAmberBg,
    padding: 6,
    borderRadius: borderRadius.sm,
    gap: 4,
  },
  adjNeedsText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.statusAmberText,
    flex: 1,
  },
  actionButtonsContainer: {
    gap: 6,
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: colors.surfaceContainerHigh,
  },
  actionButtonsRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 6,
  },
  dismissButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    backgroundColor: colors.surfaceContainerLowest,
  },
  dismissButtonText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.secondary,
  },
  naButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    backgroundColor: colors.surfaceContainerLow,
  },
  naButtonText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.onSurfaceVariant,
  },
  correctButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.primary,
    backgroundColor: '#e8f0fe',
  },
  correctButtonText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.primary,
  },
  requestImageButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.statusAmberText,
    backgroundColor: colors.statusAmberBg,
  },
  requestImageButtonText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.statusAmberText,
  },
  confirmButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: borderRadius.lg,
    backgroundColor: colors.primary,
  },
  confirmButtonText: {
    ...typography.caption,
    fontWeight: '700',
    color: colors.onPrimary,
  },
  continueButton: {
    backgroundColor: colors.primary,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: borderRadius.lg,
    marginTop: spacing.tight,
  },
  continueButtonDisabled: {
    backgroundColor: colors.statusAmberText,
  },
  continueButtonText: {
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
  modalSub: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.onSurface,
  },
  modalStatutory: {
    ...typography.caption,
    fontSize: 10,
    color: colors.onSurfaceVariant,
    fontStyle: 'italic',
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
  modalTextArea: {
    minHeight: 70,
    textAlignVertical: 'top',
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
  modalConfirmBtn: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: borderRadius.lg,
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: 120,
  },
  btnRed: { backgroundColor: colors.statusRedText },
  btnGreen: { backgroundColor: colors.statusGreenText },
  btnGrey: { backgroundColor: colors.onSurfaceVariant },
  btnBlue: { backgroundColor: colors.primary },
  modalConfirmText: {
    ...typography.bodySm,
    fontWeight: '700',
    color: colors.onPrimary,
  },
});
