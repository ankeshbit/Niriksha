import React, { useState, useCallback } from 'react';
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
import { SafeAreaView } from 'react-native-safe-area-context';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { BottomNav } from '../components/BottomNav';
import { ProfileAvatar } from '../components/ProfileAvatar';
import { api, classifyFetchError } from '../services/api';
import { useNavigation, useRoute, useFocusEffect, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

type AdjudicationAction = 'CONFIRMED' | 'DISMISSED' | 'NOT_APPLICABLE' | 'CORRECTED';

export const FindingsScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'Findings'>>();
  const { inspectionId, inspectionNumber, filter: initialFilter } = route.params;

  const targetId = inspectionId || inspectionNumber;

  const [activeFilter, setActiveFilter] = useState<'pending_adjudication' | 'all'>(
    initialFilter === 'pending_adjudication' ? 'pending_adjudication' : 'all'
  );

  React.useEffect(() => {
    if (route.params?.filter) {
      setActiveFilter(route.params.filter);
    }
  }, [route.params?.filter]);

  const [findings, setFindings] = useState<any[]>([]);
  const [pendingList, setPendingList] = useState<any[] | null>(null);
  const [summary, setSummary] = useState<any>(null);
  const [inspection, setInspection] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);

  // Adjudication Modal state
  const [adjudicatingFinding, setAdjudicatingFinding] = useState<any | null>(null);
  const [actionType, setActionType] = useState<AdjudicationAction>('CONFIRMED');
  const [adjudicationNotes, setAdjudicationNotes] = useState('');
  const [correctedValue, setCorrectedValue] = useState('');
  const [savingAction, setSavingAction] = useState(false);
  const [submittingFindingId, setSubmittingFindingId] = useState<string | null>(null);
  const [navigatingToReview, setNavigatingToReview] = useState(false);

  const loadFindings = async () => {
    if (!targetId) {
      setError('Unable to load inspection findings: No inspection ID provided.');
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);

      // Concurrently fetch compliance summary, inspection details, pending findings, and all findings
      const [summaryRes, inspRes, pendingRes, allRes] = await Promise.allSettled([
        api.getComplianceSummary(targetId),
        api.getInspection(targetId),
        api.getFindings(targetId, { status: 'pending_adjudication' }),
        api.getFindings(targetId),
      ]);

      if (inspRes.status === 'fulfilled' && inspRes.value) {
        setInspection(inspRes.value);
      }

      if (summaryRes.status === 'fulfilled' && summaryRes.value) {
        setSummary(summaryRes.value);
      }

      let allFindingsList: any[] = [];
      if (allRes.status === 'fulfilled' && Array.isArray(allRes.value)) {
        allFindingsList = allRes.value;
      } else if (summaryRes.status === 'fulfilled' && Array.isArray(summaryRes.value?.findings)) {
        allFindingsList = summaryRes.value.findings;
      }
      setFindings(allFindingsList);

      if (pendingRes.status === 'fulfilled' && Array.isArray(pendingRes.value)) {
        setPendingList(pendingRes.value);
      } else {
        setPendingList(allFindingsList.filter(isFindingPendingAdjudication));
      }
    } catch (err: any) {
      console.error('Failed to load live findings for inspection', targetId, err);
      setError('Unable to load inspection findings');
      setFindings([]);
      setPendingList([]);
      setSummary(null);
    } finally {
      setLoading(false);
    }
  };

  // Refetch live database state whenever screen is focused
  useFocusEffect(
    useCallback(() => {
      loadFindings();
    }, [targetId])
  );

  const handleRunEvaluation = async () => {
    if (!targetId) return;
    try {
      setEvaluating(true);
      await api.evaluateRules(targetId);
      await loadFindings();
    } catch (err: any) {
      Alert.alert('Evaluation Error', err.message || 'Failed to run statutory rule evaluation.');
    } finally {
      setEvaluating(false);
    }
  };

  const openModal = (finding: any, action: AdjudicationAction) => {
    setAdjudicatingFinding(finding);
    setActionType(action);
    setCorrectedValue(finding.corrected_value || finding.extracted_value || '');
    const defaultNotes: Record<AdjudicationAction, string> = {
      CONFIRMED: finding.adjudication_notes || 'Confirmed non-compliance on physical inspection.',
      DISMISSED: finding.adjudication_notes || 'Dismissed: Verified statutory exemption applies.',
      NOT_APPLICABLE: finding.adjudication_notes || 'Rule is not applicable to this commodity category.',
      CORRECTED: finding.adjudication_notes || 'Corrected statutory label information.',
    };
    setAdjudicationNotes(defaultNotes[action]);
  };

  const handleDirectAdjudicate = async (finding: any, action: AdjudicationAction) => {
    if (!finding?.id || submittingFindingId) return;

    if (action === 'CORRECTED') {
      openModal(finding, 'CORRECTED');
      return;
    }

    setSubmittingFindingId(finding.id);
    try {
      const defaultNotes: Record<AdjudicationAction, string> = {
        CONFIRMED: 'Confirmed non-compliance on physical inspection.',
        DISMISSED: 'Dismissed: Verified statutory exemption applies.',
        NOT_APPLICABLE: 'Rule is not applicable to this commodity category.',
        CORRECTED: '',
      };

      await api.adjudicateFinding(finding.id, {
        action,
        notes: defaultNotes[action] || undefined,
      });

      // Refetch live canonical state from backend
      await loadFindings();
    } catch (err: any) {
      console.error('Adjudication failed:', err);
      const classified = classifyFetchError(err);
      Alert.alert('Adjudication Error', classified.userMessage || 'Could not save adjudication decision.');
    } finally {
      setSubmittingFindingId(null);
    }
  };

  const handleRequestNewEvidence = async (finding: any) => {
    if (!finding?.id || submittingFindingId) return;

    setSubmittingFindingId(finding.id);
    try {
      await api.requestNewImage(finding.id);
      await loadFindings();
      Alert.alert(
        'Evidence Requested',
        `Finding "${finding.title}" is now awaiting additional evidence. It remains pending adjudication until new photographic evidence is reviewed.`,
        [
          { text: 'Done', style: 'default' },
          {
            text: 'Capture Now',
            onPress: () =>
              navigation.navigate('CaptureImages', {
                inspectionId: targetId || '',
                inspectionNumber: displayInspectionNumber,
              }),
          },
        ]
      );
    } catch (err: any) {
      console.error('Request new evidence failed:', err);
      const classified = classifyFetchError(err);
      Alert.alert('Error', classified.userMessage || 'Could not request new evidence.');
    } finally {
      setSubmittingFindingId(null);
    }
  };

  const handleSaveAdjudication = async () => {
    if (!adjudicatingFinding) return;
    if (!adjudicationNotes.trim() && actionType !== 'CORRECTED') {
      Alert.alert('Required Note', 'Please provide an inspector statutory remark.');
      return;
    }
    if (actionType === 'CORRECTED' && !correctedValue.trim()) {
      Alert.alert('Required Value', 'Please enter the corrected value before saving.');
      return;
    }

    setSavingAction(true);
    setSubmittingFindingId(adjudicatingFinding.id);
    try {
      await api.adjudicateFinding(adjudicatingFinding.id, {
        action: actionType,
        notes: adjudicationNotes.trim() || undefined,
        corrected_value: actionType === 'CORRECTED' ? correctedValue.trim() : undefined,
      });

      await loadFindings();
      setAdjudicatingFinding(null);
    } catch (err: any) {
      const classified = classifyFetchError(err);
      Alert.alert('Error', classified.userMessage || 'Could not save finding decision.');
    } finally {
      setSavingAction(false);
      setSubmittingFindingId(null);
    }
  };

  const handleProceedToReview = async () => {
    if (!targetId || navigatingToReview) return;
    setNavigatingToReview(true);
    try {
      await Promise.allSettled([
        api.getComplianceSummary(targetId),
        api.getInspection(targetId),
      ]);
    } catch (e) {
      console.warn('Pre-navigation refresh warning:', e);
    } finally {
      setNavigatingToReview(false);
      navigation.navigate('ReviewAndSubmit', {
        inspectionId: targetId || '',
        inspectionNumber: displayInspectionNumber,
      });
    }
  };

  // ── Card 1: compliant_checks ──────────────────────────────────────────────
  // Prefer semantically-named field, fall back to backward-compat alias, then
  // compute locally from findings (PASS + NOT_APPLICABLE + DISMISSED/CORRECTED).
  const passedCount = summary?.compliant_checks ?? summary?.no_potential_violations ?? (findings ? findings.filter((f) =>
    ((['PASS', 'NOT_APPLICABLE'].includes(f.result_state)) &&
      f.adjudication_status !== 'CONFIRMED' &&
      f.adjudication_status !== 'NEEDS_MORE_EVIDENCE') ||
    f.adjudication_status === 'DISMISSED' ||
    f.adjudication_status === 'CORRECTED'
  ).length : 0);

  // ── Card 2: potential_non_compliance ──────────────────────────────────────
  const potentialCount = summary?.potential_non_compliance ?? (findings ? findings.filter((f) =>
    (f.result_state === 'POTENTIAL_NON_COMPLIANCE' &&
      f.adjudication_status !== 'DISMISSED' &&
      f.adjudication_status !== 'NOT_APPLICABLE' &&
      f.adjudication_status !== 'CORRECTED') ||
    (f.adjudication_status === 'CONFIRMED' && f.result_state !== 'POTENTIAL_NON_COMPLIANCE')
  ).length : 0);

  // ── Card 3: needs_manual_verification ────────────────────────────────────
  // Excludes checks that are already in the potential_nc bucket.
  const needsVerificationCount = summary?.needs_manual_verification ?? (findings ? findings.filter((f) =>
    (['NEEDS_MANUAL_VERIFICATION', 'INSUFFICIENT_EVIDENCE'].includes(f.result_state) &&
      f.adjudication_status !== 'CONFIRMED' &&
      f.adjudication_status !== 'DISMISSED' &&
      f.adjudication_status !== 'NOT_APPLICABLE' &&
      f.adjudication_status !== 'CORRECTED') ||
    f.adjudication_status === 'NEEDS_MORE_EVIDENCE'
  ).length : 0);

  // ── Card 4: warnings — data quality only ─────────────────────────────────
  // Only CATEGORY_B_DATA_QUALITY checks that are NOT already in compliant or
  // manual_verification buckets (avoids double-counting with both buckets).
  const warningsCount = summary?.warnings ?? (findings ? findings.filter((f) =>
    (f.rule_code?.includes('DATA_QUAL') || f.category === 'DATA_QUALITY' || f.category === 'CATEGORY_B_DATA_QUALITY') &&
    f.result_state !== 'PASS' &&
    f.result_state !== 'NOT_APPLICABLE' &&
    f.adjudication_status !== 'DISMISSED' &&
    f.adjudication_status !== 'CORRECTED'
  ).length : 0);

  const isFindingPendingAdjudication = (f: any): boolean => {
    if (typeof f.is_pending_adjudication === 'boolean') {
      return f.is_pending_adjudication;
    }
    const resultState = (f.result_state || '').toUpperCase();
    const isNonPass = resultState !== '' && resultState !== 'PASS' && resultState !== 'NOT_APPLICABLE';
    const adjStatus = (f.adjudication_status || '').toUpperCase();
    const resolvedActions = ['CONFIRMED', 'DISMISSED', 'NOT_APPLICABLE', 'CORRECTED'];
    const isResolved = resolvedActions.includes(adjStatus);
    return isNonPass && !isResolved;
  };

  const pendingFindings = (
    pendingList !== null ? pendingList : findings.filter(isFindingPendingAdjudication)
  ).filter(isFindingPendingAdjudication);

  const displayedFindings = activeFilter === 'pending_adjudication' ? pendingFindings : findings;

  const authoritativePendingCount =
    typeof summary?.pending_adjudication_count === 'number'
      ? summary.pending_adjudication_count
      : pendingFindings.length;

  // When activeFilter is 'pending_adjudication', show only pending findings.
  // When activeFilter is 'all', show ALL findings with their current decisions/actions.
  const legalFindings = displayedFindings;
  const qualityFindings: any[] = [];

  const isEvaluationPending = summary && !summary.evaluation_completed && findings.length === 0;

  const displayInspectionNumber = inspection?.inspection_number || inspectionNumber || (inspectionId ? `ID: ${inspectionId.substring(0, 8).toUpperCase()}` : '—');

  const formattedDate = inspection?.created_at
    ? new Date(inspection.created_at).toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
    : new Date().toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      });

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
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
            <Text style={styles.headerTitle}>NiriKsha</Text>
          </View>
          <ProfileAvatar size={36} />
        </View>

        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          {/* Header Title */}
          <View style={styles.sectionHeaderBox}>
            <Text style={styles.sectionHeaderTitle}>Inspection Findings</Text>
            <Text style={styles.sectionHeaderSubtitle}>
              Inspection: {displayInspectionNumber}
            </Text>
          </View>

          {/* 4 Metric Summary Banners */}
          <View style={styles.metricsGrid}>
            {/* Card 1: Compliant Checks (Pass / Not Applicable / Dismissed) */}
            <View style={[styles.metricCard, styles.cardGreen]}>
              <MaterialIcons name="check-circle" size={22} color={colors.statusGreenText} />
              <View style={{ flex: 1 }}>
                <Text style={[styles.metricValue, { color: colors.statusGreenText }]}>{passedCount}</Text>
                <Text style={[styles.metricLabel, { color: colors.statusGreenText }]}>
                  Compliant Checks — No Violations Detected
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

            {/* Card 4: Data Quality Warnings */}
            <View style={[styles.metricCard, styles.cardGray]}>
              <MaterialIcons name="info" size={22} color={colors.secondary} />
              <View style={{ flex: 1 }}>
                <Text style={[styles.metricValue, { color: colors.secondary }]}>{warningsCount}</Text>
                <Text style={[styles.metricLabel, { color: colors.secondary }]}>Data Quality Warnings</Text>
              </View>
            </View>
          </View>

          {loading ? (
            <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
          ) : error ? (
            /* Explicit Error State with Retry button */
            <View style={styles.errorCard}>
              <MaterialIcons name="error-outline" size={36} color={colors.statusRedText} />
              <Text style={styles.errorTitle}>Unable to load inspection findings</Text>
              <Text style={styles.errorSubtitle}>{error}</Text>
              <TouchableOpacity style={styles.retryBtn} onPress={loadFindings} activeOpacity={0.8}>
                <MaterialIcons name="refresh" size={18} color="#ffffff" />
                <Text style={styles.retryBtnText}>Retry</Text>
              </TouchableOpacity>
            </View>
          ) : isEvaluationPending ? (
            /* Explicit Pending Evaluation State */
            <View style={styles.pendingCard}>
              <MaterialIcons name="hourglass-empty" size={32} color={colors.statusAmberText} />
              <View style={{ flex: 1 }}>
                <Text style={styles.pendingTitle}>Compliance evaluation pending</Text>
                <Text style={styles.pendingSubtitle}>
                  Declarations have been extracted, but statutory compliance rules have not yet been evaluated for this inspection.
                </Text>
              </View>
              <TouchableOpacity
                style={styles.evaluateBtn}
                onPress={handleRunEvaluation}
                disabled={evaluating}
                activeOpacity={0.8}
              >
                {evaluating ? (
                  <ActivityIndicator size="small" color="#ffffff" />
                ) : (
                  <>
                    <MaterialIcons name="play-arrow" size={18} color="#ffffff" />
                    <Text style={styles.evaluateBtnText}>Evaluate Rules</Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          ) : (
            <>
              {/* Segmented Filter: Pending Adjudication vs All Findings */}
              <View style={styles.filterTabContainer}>
                <TouchableOpacity
                  style={[
                    styles.filterTab,
                    activeFilter === 'pending_adjudication' && styles.filterTabActive,
                  ]}
                  onPress={() => setActiveFilter('pending_adjudication')}
                  activeOpacity={0.8}
                >
                  <MaterialIcons
                    name="gavel"
                    size={16}
                    color={activeFilter === 'pending_adjudication' ? colors.onPrimary : colors.primary}
                  />
                  <Text
                    style={[
                      styles.filterTabText,
                      activeFilter === 'pending_adjudication' && styles.filterTabTextActive,
                    ]}
                  >
                    Pending Adjudication ({authoritativePendingCount})
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[
                    styles.filterTab,
                    activeFilter === 'all' && styles.filterTabActive,
                  ]}
                  onPress={() => setActiveFilter('all')}
                  activeOpacity={0.8}
                >
                  <MaterialIcons
                    name="list"
                    size={16}
                    color={activeFilter === 'all' ? colors.onPrimary : colors.secondary}
                  />
                  <Text
                    style={[
                      styles.filterTabText,
                      activeFilter === 'all' && styles.filterTabTextActive,
                    ]}
                  >
                    All Findings ({summary?.total_findings ?? findings.length})
                  </Text>
                </TouchableOpacity>
              </View>

              {activeFilter === 'pending_adjudication' && pendingFindings.length === 0 ? (
                <View style={styles.emptyPendingCard}>
                  <MaterialIcons name="verified" size={48} color={colors.statusGreenText} />
                  <Text style={styles.emptyPendingTitle}>No findings pending adjudication</Text>
                  <Text style={styles.emptyPendingSubtitle}>
                    All statutory compliance findings have been reviewed and adjudicated.
                  </Text>
                  <View style={styles.emptyPendingActions}>
                    <TouchableOpacity
                      style={styles.viewAllFindingsBtn}
                      onPress={() => setActiveFilter('all')}
                      activeOpacity={0.8}
                    >
                      <MaterialIcons name="visibility" size={16} color={colors.primary} />
                      <Text style={styles.viewAllFindingsBtnText}>View All Findings ({summary?.total_findings ?? findings.length})</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ) : (
                <>
                  {/* Category A: Legal Compliance Checks / Pending Findings */}
                  <View style={styles.findingSectionCard}>
                    <View style={[styles.sectionBanner, styles.sectionBannerBlue]}>
                      <View style={styles.sectionBannerTitleRow}>
                        <MaterialIcons name="balance" size={18} color={colors.primary} />
                        <Text style={styles.sectionBannerTitle}>
                          {activeFilter === 'pending_adjudication'
                            ? 'FINDINGS REQUIRING ADJUDICATION'
                            : 'LEGAL COMPLIANCE CHECKS'}
                        </Text>
                      </View>
                      <Text style={styles.sectionBannerSub}>
                        {activeFilter === 'pending_adjudication'
                          ? `${legalFindings.length} finding${legalFindings.length === 1 ? '' : 's'} require inspector action before report submission`
                          : 'Category A — Legal / Statutory Compliance'}
                      </Text>
                    </View>

                    {legalFindings.length === 0 ? (
                      <View style={styles.emptyFindingRow}>
                        <MaterialIcons name="check-circle-outline" size={28} color={colors.statusGreenText} />
                        <Text style={styles.emptyFindingText}>
                          {activeFilter === 'pending_adjudication'
                            ? 'No findings pending adjudication.'
                            : 'No legal non-compliance findings detected.'}
                        </Text>
                      </View>
                    ) : (
                      legalFindings.map((finding, idx) => {
                    const isLast = idx === legalFindings.length - 1;
                    const isResolved = [
                      'CONFIRMED',
                      'DISMISSED',
                      'NOT_APPLICABLE',
                      'CORRECTED',
                    ].includes(finding.adjudication_status);
                    const isAwaitingEvidence = finding.adjudication_status === 'NEEDS_MORE_EVIDENCE';
                    const isSubmittingThis = submittingFindingId === finding.id;

                    const isFail =
                      (finding.result_state === 'POTENTIAL_NON_COMPLIANCE' &&
                        finding.adjudication_status !== 'DISMISSED' &&
                        finding.adjudication_status !== 'NOT_APPLICABLE') ||
                      finding.adjudication_status === 'CONFIRMED';
                    const isWarn =
                      finding.result_state === 'NEEDS_MANUAL_VERIFICATION' ||
                      finding.result_state === 'INSUFFICIENT_EVIDENCE' ||
                      isAwaitingEvidence;

                    const evidenceList = finding.evidence || [];
                    const firstEvidence = evidenceList.length > 0 ? evidenceList[0] : null;

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
                            {/* Rule Code & Category Badges */}
                            <View style={styles.ruleCodeRow}>
                              {finding.rule_code && (
                                <View style={styles.ruleCodeBadge}>
                                  <Text style={styles.ruleCodeText}>{finding.rule_code}</Text>
                                </View>
                              )}
                              {finding.statutory_reference && (
                                <Text style={styles.statutoryRefText} numberOfLines={1}>
                                  {finding.statutory_reference}
                                </Text>
                              )}
                            </View>

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
                                  {isResolved
                                    ? `Decision: ${finding.adjudication_status}`
                                    : isAwaitingEvidence
                                    ? 'Awaiting Evidence'
                                    : isFail
                                    ? 'Potential Non-Compliance'
                                    : isWarn
                                    ? 'Needs Manual Verification'
                                    : 'Compliant'}
                                </Text>
                              </View>
                            </View>

                            {/* Extracted Value Display if present */}
                            {finding.extracted_value ? (
                              <View style={styles.extractedValueBox}>
                                <Text style={styles.extractedValueLabel}>Detected Value:</Text>
                                <Text style={styles.extractedValueContent}>{finding.extracted_value}</Text>
                              </View>
                            ) : null}

                            {/* Statutory Explanation */}
                            <Text style={styles.findingDescText}>
                              {finding.explanation || finding.description || 'Statutory rule verification executed.'}
                            </Text>

                            {/* Physical Net Quantity Limitation Notice */}
                            {(finding.rule_code === 'PCR_RULE_06_1_C' || (finding.title && finding.title.toLowerCase().includes('net quantity'))) && (
                              <View style={styles.physicalNoticeBox}>
                                <MaterialIcons name="info-outline" size={14} color={colors.onSurfaceVariant} />
                                <Text style={styles.physicalNoticeText}>
                                  Physical net quantity requires appropriate physical verification/testing and cannot be conclusively determined from package photographs alone.
                                </Text>
                              </View>
                            )}

                            {/* Attached Evidence Link */}
                            {firstEvidence && (
                              <View style={styles.evidenceRow}>
                                <View style={styles.evidenceLeft}>
                                  <MaterialIcons name="image" size={16} color={colors.primary} />
                                  <Text style={styles.evidenceFilename} numberOfLines={1}>
                                    {firstEvidence.highlight_text || firstEvidence.reason || 'Attached Photographic Evidence'}
                                  </Text>
                                </View>
                                <TouchableOpacity
                                  onPress={() =>
                                    navigation.navigate('EvidenceReview', {
                                      inspectionId: targetId || '',
                                      findingId: finding.id,
                                    })
                                  }
                                >
                                  <Text style={styles.viewEvidenceLink}>View Evidence</Text>
                                </TouchableOpacity>
                              </View>
                            )}

                            {/* Inspector Adjudication Actions */}
                            {isResolved ? (
                              <View style={styles.resolvedDecisionBox}>
                                <View style={styles.resolvedHeader}>
                                  <MaterialIcons name="verified" size={16} color={colors.primary} />
                                  <Text style={styles.resolvedDecisionTitle}>
                                    Decision: {finding.adjudication_status}
                                  </Text>
                                </View>
                                {finding.adjudication_notes ? (
                                  <Text style={styles.resolvedNotesText} numberOfLines={2}>
                                    Note: {finding.adjudication_notes}
                                  </Text>
                                ) : null}
                                {finding.corrected_value ? (
                                  <Text style={styles.resolvedCorrectedText}>
                                    Corrected: {finding.corrected_value}
                                  </Text>
                                ) : null}
                                <TouchableOpacity
                                  style={styles.editDecisionBtn}
                                  onPress={() => openModal(finding, finding.adjudication_status)}
                                  disabled={!!submittingFindingId}
                                  activeOpacity={0.8}
                                >
                                  <MaterialIcons name="edit" size={12} color={colors.primary} />
                                  <Text style={styles.editDecisionBtnText}>Edit Decision</Text>
                                </TouchableOpacity>
                              </View>
                            ) : (
                              <View style={styles.actionsContainer}>
                                {isAwaitingEvidence && (
                                  <View style={styles.awaitingNoticeBox}>
                                    <MaterialIcons name="add-a-photo" size={14} color={colors.statusAmberText} />
                                    <Text style={styles.awaitingNoticeText}>
                                      Additional photographic evidence requested. This finding remains pending statutory adjudication.
                                    </Text>
                                  </View>
                                )}

                                {isSubmittingThis ? (
                                  <View style={styles.actionLoadingBox}>
                                    <ActivityIndicator size="small" color={colors.primary} />
                                    <Text style={styles.actionLoadingText}>Saving statutory decision...</Text>
                                  </View>
                                ) : (
                                  <>
                                    {/* Primary Action */}
                                    <TouchableOpacity
                                      style={styles.confirmBtn}
                                      onPress={() => handleDirectAdjudicate(finding, 'CONFIRMED')}
                                      disabled={!!submittingFindingId}
                                      activeOpacity={0.85}
                                    >
                                      <MaterialIcons name="check" size={16} color="#ffffff" />
                                      <Text style={styles.confirmBtnText}>CONFIRM FINDING</Text>
                                    </TouchableOpacity>

                                    {/* Secondary Row 1 */}
                                    <View style={styles.secondaryActionsRow}>
                                      <TouchableOpacity
                                        style={styles.secondaryBtn}
                                        onPress={() => handleDirectAdjudicate(finding, 'DISMISSED')}
                                        disabled={!!submittingFindingId}
                                        activeOpacity={0.8}
                                      >
                                        <Text style={styles.secondaryBtnText} numberOfLines={2}>
                                          REJECT FINDING
                                        </Text>
                                      </TouchableOpacity>

                                      <TouchableOpacity
                                        style={styles.secondaryBtn}
                                        onPress={() => openModal(finding, 'CORRECTED')}
                                        disabled={!!submittingFindingId}
                                        activeOpacity={0.8}
                                      >
                                        <Text style={styles.secondaryBtnText} numberOfLines={2}>
                                          CORRECT INFORMATION
                                        </Text>
                                      </TouchableOpacity>
                                    </View>

                                    {/* Secondary Row 2 */}
                                    <View style={styles.secondaryActionsRow}>
                                      <TouchableOpacity
                                        style={styles.secondaryBtn}
                                        onPress={() => handleRequestNewEvidence(finding)}
                                        disabled={!!submittingFindingId}
                                        activeOpacity={0.8}
                                      >
                                        <Text style={styles.secondaryBtnText} numberOfLines={2}>
                                          REQUEST NEW EVIDENCE
                                        </Text>
                                      </TouchableOpacity>

                                      <TouchableOpacity
                                        style={styles.secondaryBtn}
                                        onPress={() => handleDirectAdjudicate(finding, 'NOT_APPLICABLE')}
                                        disabled={!!submittingFindingId}
                                        activeOpacity={0.8}
                                      >
                                        <Text style={styles.secondaryBtnText} numberOfLines={2}>
                                          NOT APPLICABLE
                                        </Text>
                                      </TouchableOpacity>
                                    </View>
                                  </>
                                )}
                              </View>
                            )}
                          </View>
                        </View>
                      </View>
                    );
                  })
                )}
              </View>
            </>
          )}

              {/* Inspection Context Card */}
              <View style={styles.contextCard}>
                <Text style={styles.contextTitle}>Inspection Context</Text>
                <View style={styles.contextItemRow}>
                  <Text style={styles.contextLabel}>Entity / Brand:</Text>
                  <Text style={styles.contextValueBold}>
                    {inspection?.product?.brand_name || inspection?.product?.product_name || '—'}
                  </Text>
                </View>
                <View style={styles.contextItemRow}>
                  <Text style={styles.contextLabel}>Location:</Text>
                  <Text style={styles.contextValue}>{inspection?.location || '—'}</Text>
                </View>
                <View style={styles.contextItemRow}>
                  <Text style={styles.contextLabel}>Date:</Text>
                  <Text style={styles.contextValue}>{formattedDate}</Text>
                </View>
              </View>

              {/* Proceed Button */}
              <TouchableOpacity
                style={styles.proceedButton}
                onPress={handleProceedToReview}
                disabled={navigatingToReview}
                activeOpacity={0.85}
              >
                {navigatingToReview ? (
                  <ActivityIndicator size="small" color={colors.onPrimary} />
                ) : (
                  <>
                    <Text style={styles.proceedButtonText}>Proceed to Review & Submit</Text>
                    <MaterialIcons name="arrow-forward" size={18} color={colors.onPrimary} />
                  </>
                )}
              </TouchableOpacity>
            </>
          )}

          <View style={styles.footerNote}>
            <Text style={styles.footerNoteText}>Smart India Hackathon 2026 Prototype • Live Neon DB</Text>
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
  errorCard: {
    backgroundColor: colors.statusRedBg,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    borderColor: colors.statusRedText,
    padding: 20,
    alignItems: 'center',
    gap: 8,
    marginVertical: 12,
  },
  errorTitle: {
    ...typography.headlineLg,
    fontSize: 15,
    fontWeight: '700',
    color: colors.statusRedText,
    textAlign: 'center',
  },
  errorSubtitle: {
    ...typography.bodySm,
    fontSize: 12,
    color: colors.statusRedText,
    textAlign: 'center',
    opacity: 0.9,
  },
  retryBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: colors.statusRedText,
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: borderRadius.DEFAULT,
    marginTop: 6,
  },
  retryBtnText: {
    ...typography.labelCaps,
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '700',
  },
  pendingCard: {
    backgroundColor: colors.statusAmberBg,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    borderColor: colors.statusAmberText,
    padding: 16,
    flexDirection: 'column',
    gap: 12,
    marginVertical: 12,
  },
  pendingTitle: {
    ...typography.sectionHeader,
    fontSize: 14,
    fontWeight: '700',
    color: colors.statusAmberText,
  },
  pendingSubtitle: {
    ...typography.bodySm,
    fontSize: 12,
    color: colors.onSurface,
    marginTop: 2,
  },
  evaluateBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: colors.statusAmberText,
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: borderRadius.DEFAULT,
    alignSelf: 'flex-start',
  },
  evaluateBtnText: {
    ...typography.labelCaps,
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '700',
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
    padding: 24,
    alignItems: 'center',
    gap: 8,
  },
  emptyFindingText: {
    ...typography.bodySm,
    fontSize: 13,
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
  ruleCodeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 4,
  },
  ruleCodeBadge: {
    backgroundColor: colors.surfaceContainerLow,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  ruleCodeText: {
    ...typography.caption,
    fontSize: 10,
    fontWeight: '700',
    color: colors.primary,
  },
  statutoryRefText: {
    ...typography.caption,
    fontSize: 10,
    color: colors.onSurfaceVariant,
    flex: 1,
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
  extractedValueBox: {
    flexDirection: 'row',
    gap: 6,
    backgroundColor: colors.surfaceContainerLow,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: borderRadius.sm,
    marginBottom: 6,
    alignItems: 'center',
  },
  extractedValueLabel: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.onSurfaceVariant,
  },
  extractedValueContent: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '700',
    color: colors.onSurface,
  },
  findingDescText: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.onSurfaceVariant,
    marginBottom: 8,
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
    flex: 1,
    marginRight: 8,
  },
  evidenceFilename: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
    flex: 1,
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
    minHeight: 44,
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
    letterSpacing: 0.5,
  },
  secondaryActionsRow: {
    flexDirection: 'row',
    gap: 8,
  },
  secondaryBtn: {
    flex: 1,
    minHeight: 44,
    paddingVertical: 8,
    paddingHorizontal: 6,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1.5,
    borderColor: colors.borderSubtle,
    backgroundColor: colors.surfaceContainerLowest,
    justifyContent: 'center',
    alignItems: 'center',
  },
  secondaryBtnText: {
    ...typography.labelCaps,
    fontSize: 11,
    lineHeight: 14,
    color: colors.primary,
    fontWeight: '700',
    textAlign: 'center',
    letterSpacing: 0.3,
  },
  resolvedDecisionBox: {
    marginTop: 10,
    padding: 12,
    backgroundColor: colors.surfaceContainerLow,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    gap: 6,
  },
  resolvedHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  resolvedDecisionTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.primary,
  },
  resolvedNotesText: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    fontStyle: 'italic',
  },
  resolvedCorrectedText: {
    fontSize: 12,
    color: colors.statusGreenText,
    fontWeight: '600',
  },
  editDecisionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    marginTop: 4,
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: borderRadius.xs,
    borderWidth: 1,
    borderColor: colors.primary,
    backgroundColor: colors.surfaceContainerLowest,
    gap: 4,
  },
  editDecisionBtnText: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.primary,
  },
  awaitingNoticeBox: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 10,
    backgroundColor: '#fff8e1',
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    borderColor: '#ffe082',
    gap: 8,
    marginBottom: 4,
  },
  awaitingNoticeText: {
    flex: 1,
    fontSize: 12,
    color: colors.statusAmberText,
    fontWeight: '500',
  },
  actionLoadingBox: {
    minHeight: 70,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 12,
  },
  actionLoadingText: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    fontWeight: '500',
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
  physicalNoticeBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceContainer,
    borderRadius: borderRadius.sm,
    paddingHorizontal: 8,
    paddingVertical: 6,
    gap: 6,
    marginVertical: 4,
  },
  physicalNoticeText: {
    flex: 1,
    ...typography.bodySm,
    fontSize: 11,
    lineHeight: 14,
    color: colors.onSurfaceVariant,
    fontStyle: 'italic',
  },
  filterTabContainer: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceContainerHigh,
    borderRadius: borderRadius.DEFAULT,
    padding: 4,
    gap: 6,
    marginVertical: 4,
  },
  filterTab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: borderRadius.sm,
    gap: 6,
  },
  filterTabActive: {
    backgroundColor: colors.primary,
  },
  filterTabText: {
    ...typography.labelCaps,
    fontSize: 12,
    fontWeight: '600',
    color: colors.onSurfaceVariant,
  },
  filterTabTextActive: {
    color: colors.onPrimary,
    fontWeight: '700',
  },
  emptyPendingCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    padding: 24,
    alignItems: 'center',
    gap: 10,
    marginVertical: 8,
  },
  emptyPendingTitle: {
    ...typography.headlineLg,
    fontSize: 16,
    fontWeight: '700',
    color: colors.onSurface,
    textAlign: 'center',
  },
  emptyPendingSubtitle: {
    ...typography.bodySm,
    fontSize: 13,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
    lineHeight: 18,
    maxWidth: 300,
  },
  emptyPendingActions: {
    flexDirection: 'column',
    gap: 10,
    width: '100%',
    marginTop: 10,
  },
  viewAllFindingsBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    borderColor: colors.primary,
    backgroundColor: colors.surfaceContainerLowest,
  },
  viewAllFindingsBtnText: {
    ...typography.labelCaps,
    color: colors.primary,
    fontWeight: '700',
    fontSize: 12,
  },
});
