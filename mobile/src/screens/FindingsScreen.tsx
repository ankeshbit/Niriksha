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
        data = evalRes.findings || [];
      }
      setFindings(data || []);
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
      `This will mark finding "${finding.title}" as needing more evidence and navigate you to capture a new package image.\n\nProceed?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Capture New Image',
          onPress: async () => {
            try {
              await api.requestNewImage(finding.id);
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
      Alert.alert('Required Note', 'Please provide an inspector statutory remark.');
      return;
    }
    if (actionType === 'CORRECTED' && !correctedValue.trim()) {
      Alert.alert('Required Value', 'Please enter the corrected value.');
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
      Alert.alert('Error', err.message || 'Could not save finding decision.');
    } finally {
      setSavingAction(false);
    }
  };

  // Counts for 4 Summary Cards (Real Database Calculated Values)
  const passedCount = findings.filter((f) => f.status === 'PASS' || f.adjudication === 'DISMISSED').length;
  const potentialCount = findings.filter((f) => f.status === 'FAIL' || f.adjudication === 'CONFIRMED').length;
  const needsVerificationCount =
    findings.filter((f) => f.status === 'WARNING' || f.adjudication === 'NEEDS_MORE_EVIDENCE' || f.status === 'NEEDS_MANUAL_VERIFICATION').length;
  const warningsCount = findings.filter((f) => f.category === 'DATA_QUALITY' || f.status === 'WARNING').length;

  const legalFindings = findings.filter((f) => f.category !== 'DATA_QUALITY');
  const qualityFindings = findings.filter((f) => f.category === 'DATA_QUALITY');

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
            <Text style={styles.headerTitle}>Legal Metrology</Text>
          </View>
          <View style={styles.avatarCircle}>
            <MaterialIcons name="person" size={20} color={colors.primary} />
          </View>
        </View>

        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          {/* Header Title */}
          <View style={styles.sectionHeaderBox}>
            <Text style={styles.sectionHeaderTitle}>Inspection Findings</Text>
            <Text style={styles.sectionHeaderSubtitle}>
              Report ID: {inspectionNumber || 'LM-2026-00891'}
            </Text>
          </View>

          {/* 4 Metric Summary Banners */}
          <View style={styles.metricsGrid}>
            {/* Card 1: Passed */}
            <View style={[styles.metricCard, styles.cardGreen]}>
              <MaterialIcons name="check-circle" size={22} color={colors.statusGreenText} />
              <View style={{ flex: 1 }}>
                <Text style={[styles.metricValue, { color: colors.statusGreenText }]}>{passedCount}</Text>
                <Text style={[styles.metricLabel, { color: colors.statusGreenText }]}>
                  No Potential Violations Detected
                </Text>
              </View>
            </View>

            {/* Card 2: Potential Findings */}
            <View style={[styles.metricCard, styles.cardRed]}>
              <MaterialIcons name="error" size={22} color={colors.statusRedText} />
              <View style={{ flex: 1 }}>
                <Text style={[styles.metricValue, { color: colors.statusRedText }]}>{potentialCount}</Text>
                <Text style={[styles.metricLabel, { color: colors.statusRedText }]}>
                  Potential Non-Compliance — Pending Inspector Confirmation
                </Text>
              </View>
            </View>

            {/* Card 3: Needs Verification */}
            <View style={[styles.metricCard, styles.cardAmber]}>
              <MaterialIcons name="warning" size={22} color={colors.statusAmberText} />
              <View style={{ flex: 1 }}>
                <Text style={[styles.metricValue, { color: colors.statusAmberText }]}>
                  {needsVerificationCount}
                </Text>
                <Text style={[styles.metricLabel, { color: colors.statusAmberText }]}>
                  Needs Manual Verification
                </Text>
              </View>
            </View>

            {/* Card 4: Warnings */}
            <View style={[styles.metricCard, styles.cardGray]}>
              <MaterialIcons name="info" size={22} color={colors.secondary} />
              <View style={{ flex: 1 }}>
                <Text style={[styles.metricValue, { color: colors.secondary }]}>{warningsCount}</Text>
                <Text style={[styles.metricLabel, { color: colors.secondary }]}>Warnings</Text>
              </View>
            </View>
          </View>

          {loading ? (
            <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
          ) : (
            <>
              {/* Category A: Legal Compliance Checks */}
              <View style={styles.findingSectionCard}>
                <View style={[styles.sectionBanner, styles.sectionBannerBlue]}>
                  <View style={styles.sectionBannerTitleRow}>
                    <MaterialIcons name="balance" size={18} color={colors.primary} />
                    <Text style={styles.sectionBannerTitle}>LEGAL COMPLIANCE CHECKS</Text>
                  </View>
                  <Text style={styles.sectionBannerSub}>Category A — Legal / Compliance</Text>
                </View>

                {legalFindings.length === 0 ? (
                  <View style={styles.emptyFindingRow}>
                    <Text style={styles.emptyFindingText}>No legal compliance issues found.</Text>
                  </View>
                ) : (
                  legalFindings.map((finding, idx) => {
                    const isLast = idx === legalFindings.length - 1;
                    const isFail = finding.status === 'FAIL' || finding.adjudication === 'CONFIRMED';
                    const isWarn = finding.status === 'WARNING';

                    return (
                      <View key={finding.id || idx} style={[styles.findingRow, !isLast && styles.rowBorder]}>
                        <View style={styles.findingRowTop}>
                          <MaterialIcons
                            name={isFail ? 'error' : isWarn ? 'warning' : 'check-circle'}
                            size={20}
                            color={isFail ? colors.statusRedText : isWarn ? colors.statusAmberText : colors.statusGreenText}
                            style={{ marginTop: 2 }}
                          />
                          <View style={{ flex: 1 }}>
                            <View style={styles.findingTitleRow}>
                              <Text style={styles.findingTitleText}>{finding.title}</Text>
                              <View
                                style={[
                                  styles.statusBadge,
                                  isFail ? styles.badgeRed : isWarn ? styles.badgeAmber : styles.badgeGreen,
                                ]}
                              >
                                <Text
                                  style={[
                                    styles.statusBadgeText,
                                    isFail ? styles.badgeTextRed : isWarn ? styles.badgeTextAmber : styles.badgeTextGreen,
                                  ]}
                                >
                                  {finding.adjudication
                                    ? `Decision: ${finding.adjudication}`
                                    : isFail
                                    ? 'Potential Non-Compliance Identified'
                                    : isWarn
                                    ? 'Review Needed'
                                    : 'Compliant'}
                                </Text>
                              </View>
                            </View>

                            <Text style={styles.findingDescText}>{finding.description}</Text>

                            {/* AI Detection Basis */}
                            <View style={styles.aiBasisBox}>
                              <Text style={styles.aiBasisLabel}>AI Detection Basis</Text>
                              <Text style={styles.aiBasisText}>
                                {finding.ai_reasoning || finding.description}
                              </Text>
                            </View>

                            {/* Evidence Attachment */}
                            <View style={styles.evidenceRow}>
                              <View style={styles.evidenceLeft}>
                                <MaterialIcons name="image" size={16} color={colors.onSurfaceVariant} />
                                <Text style={styles.evidenceFilename}>evidence_package_panel.jpg</Text>
                              </View>
                              <TouchableOpacity
                                onPress={() =>
                                  navigation.navigate('EvidenceReview', {
                                    inspectionId,
                                    findingId: finding.id,
                                  })
                                }
                              >
                                <Text style={styles.viewEvidenceLink}>View</Text>
                              </TouchableOpacity>
                            </View>

                            {/* Action Buttons */}
                            <View style={styles.actionsContainer}>
                              <TouchableOpacity
                                style={styles.confirmBtn}
                                onPress={() => openModal(finding, 'CONFIRMED')}
                                activeOpacity={0.85}
                              >
                                <MaterialIcons name="check" size={16} color="#ffffff" />
                                <Text style={styles.confirmBtnText}>Confirm Finding</Text>
                              </TouchableOpacity>

                              <View style={styles.secondaryActionsRow}>
                                <TouchableOpacity
                                  style={styles.actionBtnOutline}
                                  onPress={() => openModal(finding, 'DISMISSED')}
                                  activeOpacity={0.8}
                                >
                                  <Text style={styles.actionBtnOutlineText}>Reject Finding</Text>
                                </TouchableOpacity>

                                <TouchableOpacity
                                  style={styles.actionBtnBorder}
                                  onPress={() => openModal(finding, 'CORRECTED')}
                                  activeOpacity={0.8}
                                >
                                  <Text style={styles.actionBtnBorderText}>Correct Info</Text>
                                </TouchableOpacity>
                              </View>

                              <View style={styles.secondaryActionsRow}>
                                <TouchableOpacity
                                  style={styles.actionBtnBorder}
                                  onPress={() => handleRequestNewImage(finding)}
                                  activeOpacity={0.8}
                                >
                                  <Text style={styles.actionBtnBorderText}>Request New Image</Text>
                                </TouchableOpacity>

                                <TouchableOpacity
                                  style={styles.actionBtnBorder}
                                  onPress={() => openModal(finding, 'NOT_APPLICABLE')}
                                  activeOpacity={0.8}
                                >
                                  <Text style={styles.actionBtnBorderText}>Not Applicable</Text>
                                </TouchableOpacity>
                              </View>
                            </View>
                          </View>
                        </View>
                      </View>
                    );
                  })
                )}
              </View>

              {/* Category B: Data Quality Warnings */}
              {qualityFindings.length > 0 && (
                <View style={[styles.findingSectionCard, { marginTop: 12 }]}>
                  <View style={[styles.sectionBanner, styles.sectionBannerAmber]}>
                    <View style={styles.sectionBannerTitleRow}>
                      <MaterialIcons name="warning" size={18} color={colors.statusAmberText} />
                      <Text style={styles.sectionBannerTitle}>DATA QUALITY WARNINGS</Text>
                    </View>
                    <Text style={styles.sectionBannerSub}>Category B — Data Quality</Text>
                  </View>

                  {qualityFindings.map((finding, idx) => (
                    <View key={finding.id || idx} style={styles.findingRow}>
                      <Text style={styles.findingTitleText}>{finding.title}</Text>
                      <Text style={styles.findingDescText}>{finding.description}</Text>
                    </View>
                  ))}
                </View>
              )}

              {/* Inspection Context Card */}
              <View style={styles.contextCard}>
                <Text style={styles.contextTitle}>Inspection Context</Text>
                <View style={styles.contextItemRow}>
                  <Text style={styles.contextLabel}>Entity:</Text>
                  <Text style={styles.contextValueBold}>Agro Foods Pvt. Ltd.</Text>
                </View>
                <View style={styles.contextItemRow}>
                  <Text style={styles.contextLabel}>Location:</Text>
                  <Text style={styles.contextValue}>Sector 4 Market</Text>
                </View>
                <View style={styles.contextItemRow}>
                  <Text style={styles.contextLabel}>Date:</Text>
                  <Text style={styles.contextValue}>{todayStr}</Text>
                </View>
              </View>

              {/* Proceed Button */}
              <TouchableOpacity
                style={styles.proceedButton}
                onPress={() =>
                  navigation.navigate('ReviewAndSubmit', {
                    inspectionId,
                    inspectionNumber,
                  })
                }
                activeOpacity={0.85}
              >
                <Text style={styles.proceedButtonText}>Proceed to Review & Submit</Text>
                <MaterialIcons name="arrow-forward" size={18} color={colors.onPrimary} />
              </TouchableOpacity>
            </>
          )}

          <View style={styles.footerNote}>
            <Text style={styles.footerNoteText}>Smart India Hackathon 2026 Prototype</Text>
          </View>
        </ScrollView>

        {/* Adjudication Modal */}
        <Modal visible={!!adjudicatingFinding} transparent animationType="fade">
          <View style={styles.modalOverlay}>
            <View style={styles.modalContent}>
              <View style={styles.modalHeader}>
                <Text style={typography.sectionHeader}>
                  {actionType === 'CONFIRMED'
                    ? 'Confirm Finding'
                    : actionType === 'DISMISSED'
                    ? 'Reject Finding'
                    : actionType === 'CORRECTED'
                    ? 'Correct Information'
                    : 'Mark Not Applicable'}
                </Text>
                <TouchableOpacity onPress={() => setAdjudicatingFinding(null)}>
                  <MaterialIcons name="close" size={22} color={colors.onSurfaceVariant} />
                </TouchableOpacity>
              </View>

              <View style={styles.modalBody}>
                {actionType === 'CORRECTED' && (
                  <View style={{ gap: 4, marginBottom: 10 }}>
                    <Text style={typography.labelCaps}>Correct Value</Text>
                    <TextInput
                      style={styles.modalInput}
                      value={correctedValue}
                      onChangeText={setCorrectedValue}
                      placeholder="Enter verified label value"
                      placeholderTextColor={colors.outline}
                    />
                  </View>
                )}

                <View style={{ gap: 4 }}>
                  <Text style={typography.labelCaps}>Inspector Remarks</Text>
                  <TextInput
                    style={[styles.modalInput, { minHeight: 60, textAlignVertical: 'top' }]}
                    value={adjudicationNotes}
                    onChangeText={setAdjudicationNotes}
                    placeholder="Enter statutory reason/decision note..."
                    placeholderTextColor={colors.outline}
                    multiline
                  />
                </View>
              </View>

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={styles.modalCancelBtn}
                  onPress={() => setAdjudicatingFinding(null)}
                  disabled={savingAction}
                >
                  <Text style={styles.modalCancelText}>Cancel</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.modalSaveBtn}
                  onPress={handleSaveAdjudication}
                  disabled={savingAction}
                  activeOpacity={0.85}
                >
                  {savingAction ? (
                    <ActivityIndicator size="small" color={colors.onPrimary} />
                  ) : (
                    <Text style={styles.modalSaveText}>Save Decision</Text>
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
  avatarCircle: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    alignItems: 'center',
    justifyContent: 'center',
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
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
  },
  metricsGrid: {
    gap: 8,
  },
  metricCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    padding: spacing.stackMd,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    gap: 10,
  },
  cardGreen: {
    backgroundColor: colors.statusGreenBg,
  },
  cardRed: {
    backgroundColor: colors.statusRedBg,
  },
  cardAmber: {
    backgroundColor: colors.statusAmberBg,
  },
  cardGray: {
    backgroundColor: colors.surfaceContainerHigh,
  },
  metricValue: {
    ...typography.headlineLg,
    fontSize: 18,
    lineHeight: 24,
    fontWeight: '700',
  },
  metricLabel: {
    ...typography.labelCaps,
    fontSize: 11,
    lineHeight: 15,
    marginTop: 2,
  },
  findingSectionCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    overflow: 'hidden',
  },
  sectionBanner: {
    padding: spacing.stackMd,
    borderLeftWidth: 4,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    gap: 2,
  },
  sectionBannerBlue: {
    borderLeftColor: colors.primary,
    backgroundColor: colors.surfaceContainerLowest,
  },
  sectionBannerAmber: {
    borderLeftColor: colors.statusAmberText,
    backgroundColor: colors.surfaceContainerLowest,
  },
  sectionBannerTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  sectionBannerTitle: {
    ...typography.sectionHeader,
    fontSize: 14,
    fontWeight: '700',
    color: colors.primary,
  },
  sectionBannerSub: {
    ...typography.labelCaps,
    fontSize: 10,
    color: colors.onSurfaceVariant,
    opacity: 0.7,
  },
  emptyFindingRow: {
    padding: 16,
    alignItems: 'center',
  },
  emptyFindingText: {
    ...typography.bodySm,
    color: colors.onSurfaceVariant,
  },
  findingRow: {
    padding: spacing.stackMd,
  },
  rowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  findingRowTop: {
    flexDirection: 'row',
    gap: 10,
  },
  findingTitleRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 6,
    marginBottom: 4,
  },
  findingTitleText: {
    ...typography.labelCaps,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '700',
    color: colors.onSurface,
    flex: 1,
  },
  statusBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: borderRadius.DEFAULT,
  },
  badgeRed: {
    backgroundColor: colors.statusRedBg,
  },
  badgeAmber: {
    backgroundColor: colors.statusAmberBg,
  },
  badgeGreen: {
    backgroundColor: colors.statusGreenBg,
  },
  statusBadgeText: {
    ...typography.caption,
    fontSize: 10,
    fontWeight: '600',
  },
  badgeTextRed: {
    color: colors.statusRedText,
  },
  badgeTextAmber: {
    color: colors.statusAmberText,
  },
  badgeTextGreen: {
    color: colors.statusGreenText,
  },
  findingDescText: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.onSurfaceVariant,
    marginBottom: 8,
  },
  aiBasisBox: {
    backgroundColor: colors.surfaceContainerLow,
    padding: spacing.stackSm,
    borderRadius: borderRadius.DEFAULT,
    gap: 2,
    marginBottom: 8,
  },
  aiBasisLabel: {
    ...typography.labelCaps,
    fontSize: 11,
    fontWeight: '600',
    color: colors.onSurface,
  },
  aiBasisText: {
    ...typography.bodySm,
    fontSize: 12,
    lineHeight: 16,
    color: colors.onSurfaceVariant,
  },
  evidenceRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    padding: spacing.stackSm,
    marginBottom: 12,
  },
  evidenceLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  evidenceFilename: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
  },
  viewEvidenceLink: {
    ...typography.labelCaps,
    fontSize: 12,
    fontWeight: '600',
    color: colors.primary,
    textDecorationLine: 'underline',
  },
  actionsContainer: {
    gap: 8,
  },
  confirmBtn: {
    backgroundColor: colors.primary,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: borderRadius.DEFAULT,
    gap: 6,
  },
  confirmBtnText: {
    ...typography.labelCaps,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
    color: '#ffffff',
  },
  secondaryActionsRow: {
    flexDirection: 'row',
    gap: 8,
  },
  actionBtnOutline: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    borderColor: colors.primary,
  },
  actionBtnOutlineText: {
    ...typography.labelCaps,
    fontSize: 11,
    color: colors.primary,
    fontWeight: '600',
  },
  actionBtnBorder: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    backgroundColor: colors.surfaceContainerLowest,
  },
  actionBtnBorderText: {
    ...typography.labelCaps,
    fontSize: 11,
    color: colors.onSurface,
  },
  contextCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    padding: spacing.stackMd,
    gap: 6,
  },
  contextTitle: {
    ...typography.labelCaps,
    fontSize: 12,
    fontWeight: '700',
    color: colors.onSurface,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    paddingBottom: 4,
    marginBottom: 2,
  },
  contextItemRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  contextLabel: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
  },
  contextValue: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurface,
  },
  contextValueBold: {
    ...typography.caption,
    fontSize: 12,
    fontWeight: '700',
    color: colors.onSurface,
  },
  proceedButton: {
    backgroundColor: colors.primary,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    borderRadius: borderRadius.xl,
    gap: 8,
    marginTop: 8,
  },
  proceedButtonText: {
    ...typography.sectionHeader,
    fontSize: 15,
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
    gap: 8,
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
