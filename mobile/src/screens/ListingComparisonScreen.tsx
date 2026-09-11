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
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { BottomNav } from '../components/BottomNav';
import { ProfileAvatar } from '../components/ProfileAvatar';
import { api } from '../services/api';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

type AdjudicationStatus = 'VERIFIED_MATCH' | 'CONFIRMED_DISCREPANCY' | 'DISMISSED_DISCREPANCY';

export const ListingComparisonScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'ListingComparison'>>();
  const { inspectionId, inspectionNumber } = route.params;

  const [loading, setLoading] = useState(true);
  const [comparing, setComparing] = useState(false);
  const [summaryData, setSummaryData] = useState<any | null>(null);

  // Modal for Adjudication
  const [activeItem, setActiveItem] = useState<any | null>(null);
  const [adjudicationOutcome, setAdjudicationOutcome] = useState<AdjudicationStatus>('CONFIRMED_DISCREPANCY');
  const [inspectorNotes, setInspectorNotes] = useState('');
  const [savingAdjudication, setSavingAdjudication] = useState(false);

  const loadData = async () => {
    try {
      setLoading(true);
      let data = await api.getListingComparison(inspectionId).catch(() => null);
      if (!data || !data.comparisons || data.comparisons.length === 0) {
        // Run comparison if not yet generated
        data = await api.compareProductListing(inspectionId).catch(() => null);
      }
      setSummaryData(data);
    } catch (err) {
      console.error('Failed to load comparison data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [inspectionId]);

  const handleRerunComparison = async () => {
    try {
      setComparing(true);
      const res = await api.compareProductListing(inspectionId);
      setSummaryData(res);
      Alert.alert('Comparison Updated', 'Listing data compared against latest package OCR declarations.');
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to compare listing data.');
    } finally {
      setComparing(false);
    }
  };

  const openAdjudicationModal = (item: any) => {
    setActiveItem(item);
    setAdjudicationOutcome(
      item.comparison_status === 'MATCH' ? 'VERIFIED_MATCH' : 'CONFIRMED_DISCREPANCY'
    );
    setInspectorNotes(item.inspector_remarks || '');
  };

  const submitAdjudication = async () => {
    if (!activeItem) return;
    try {
      setSavingAdjudication(true);
      const updated = await api.adjudicateListingComparison(inspectionId, activeItem.id, {
        status: adjudicationOutcome,
        remarks: inspectorNotes.trim() || undefined,
      });

      // Update local state
      if (summaryData && summaryData.comparisons) {
        const updatedList = summaryData.comparisons.map((c: any) =>
          c.id === activeItem.id ? updated : c
        );
        setSummaryData({ ...summaryData, comparisons: updatedList });
      }
      setActiveItem(null);
      Alert.alert('Adjudication Saved', 'Discrepancy finding recorded with inspector provenance.');
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to save adjudication.');
    } finally {
      setSavingAdjudication(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'MATCH':
        return { label: '✓ Match', color: '#16a34a', bg: '#dcfce7' };
      case 'MISMATCH':
        return { label: '⚠ Conflict', color: '#dc2626', bg: '#fee2e2' };
      case 'MISSING_ON_LISTING':
        return { label: 'ℹ Missing on Listing', color: '#2563eb', bg: '#dbeafe' };
      case 'MISSING_ON_PACKAGE':
        return { label: '❓ Missing on Package', color: '#7c3aed', bg: '#ede9fe' };
      case 'UNCERTAIN':
      default:
        return { label: '⏳ Uncertain', color: '#d97706', bg: '#fef3c7' };
    }
  };

  const formatFieldName = (f: string) => {
    return f
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (l) => l.toUpperCase());
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={styles.loadingText}>Comparing product listing with package evidence...</Text>
        </View>
      </SafeAreaView>
    );
  }

  const comparisons = summaryData?.comparisons || [];

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity
          style={styles.backButton}
          onPress={() => navigation.goBack()}
          accessibilityRole="button"
          accessibilityLabel="Back"
        >
          <MaterialIcons name="arrow-back" size={24} color={colors.onSurface} />
        </TouchableOpacity>
        <View style={styles.headerTitles}>
          <Text style={styles.headerTitle}>Product Information Consistency</Text>
          <Text style={styles.headerSubtitle}>
            {inspectionNumber || summaryData?.inspection_number || 'E-Commerce Compliance'}
          </Text>
        </View>
        <ProfileAvatar />
      </View>

      <ScrollView style={styles.scrollView} contentContainerStyle={styles.contentContainer}>
        {/* Metric Summary Bar */}
        <View style={styles.summaryBar}>
          <View style={styles.summaryChip}>
            <Text style={[styles.summaryCount, { color: '#16a34a' }]}>
              {summaryData?.matches_count ?? 0}
            </Text>
            <Text style={styles.summaryLabel}>Matches</Text>
          </View>
          <View style={styles.summaryDivider} />
          <View style={styles.summaryChip}>
            <Text style={[styles.summaryCount, { color: '#dc2626' }]}>
              {summaryData?.mismatches_count ?? 0}
            </Text>
            <Text style={styles.summaryLabel}>Conflicts</Text>
          </View>
          <View style={styles.summaryDivider} />
          <View style={styles.summaryChip}>
            <Text style={[styles.summaryCount, { color: '#2563eb' }]}>
              {summaryData?.missing_on_listing_count ?? 0}
            </Text>
            <Text style={styles.summaryLabel}>Missing Listing</Text>
          </View>
          <View style={styles.summaryDivider} />
          <View style={styles.summaryChip}>
            <Text style={[styles.summaryCount, { color: '#d97706' }]}>
              {summaryData?.uncertain_count ?? 0}
            </Text>
            <Text style={styles.summaryLabel}>Uncertain</Text>
          </View>
        </View>

        {/* Consistency Overview Table */}
        <View style={styles.tableCard}>
          <Text style={styles.cardSectionTitle}>PRODUCT INFORMATION CONSISTENCY</Text>
          <Text style={styles.cardSectionSub}>
            Field-by-field verification between online listing claims and package evidence
          </Text>

          <View style={styles.tableBody}>
            {comparisons.map((item: any) => {
              const badge = getStatusBadge(item.comparison_status);
              return (
                <View key={item.id} style={styles.tableRow}>
                  <Text style={styles.tableField}>{formatFieldName(item.field_name)}</Text>
                  <View style={[styles.badge, { backgroundColor: badge.bg }]}>
                    <Text style={[styles.badgeText, { color: badge.color }]}>{badge.label}</Text>
                  </View>
                </View>
              );
            })}
          </View>
        </View>

        {/* Detailed Discrepancy & Item Cards */}
        <Text style={styles.sectionHeader}>Evidence & Discrepancy Review</Text>

        {comparisons.map((item: any) => {
          const badge = getStatusBadge(item.comparison_status);
          const isConflict = item.comparison_status !== 'MATCH';

          return (
            <View
              key={item.id}
              style={[
                styles.itemCard,
                isConflict ? styles.itemCardConflict : styles.itemCardMatch,
              ]}
            >
              <View style={styles.itemCardHeader}>
                <View style={styles.itemTitleRow}>
                  <MaterialIcons
                    name={isConflict ? 'error-outline' : 'check-circle-outline'}
                    size={20}
                    color={badge.color}
                  />
                  <Text style={styles.itemFieldName}>{formatFieldName(item.field_name)}</Text>
                </View>
                <View style={[styles.badge, { backgroundColor: badge.bg }]}>
                  <Text style={[styles.badgeText, { color: badge.color }]}>{badge.label}</Text>
                </View>
              </View>

              {/* Side-by-side Values */}
              <View style={styles.comparisonBox}>
                <View style={styles.valueColumn}>
                  <Text style={styles.valueLabel}>ONLINE LISTING</Text>
                  <Text style={styles.valueText}>
                    {item.listing_value ? item.listing_value : '(Not provided)'}
                  </Text>
                  <Text style={styles.provenanceTag}>Source: {item.listing_provenance}</Text>
                </View>

                <View style={styles.verticalDivider} />

                <View style={styles.valueColumn}>
                  <Text style={styles.valueLabel}>PHYSICAL PACKAGE</Text>
                  <Text style={styles.valueText}>
                    {item.package_value ? item.package_value : '(Not detected in OCR)'}
                  </Text>
                  <Text style={styles.provenanceTag}>
                    Evidence: {item.package_provenance} (Conf: {(item.ocr_confidence * 100).toFixed(0)}%)
                  </Text>
                </View>
              </View>

              {/* Difference Explanation */}
              {item.difference_explanation ? (
                <View style={styles.explanationBox}>
                  <Text style={styles.explanationText}>{item.difference_explanation}</Text>
                </View>
              ) : null}

              {/* Package OCR Evidence snippet */}
              {item.package_ocr_evidence ? (
                <View style={styles.evidenceSnippetBox}>
                  <Text style={styles.evidenceSnippetLabel}>Raw Package OCR Snippet:</Text>
                  <Text style={styles.evidenceSnippetText}>"{item.package_ocr_evidence}"</Text>
                </View>
              ) : null}

              {/* Applicable Rule Citation */}
              {item.applicable_rule_code ? (
                <View style={styles.ruleBox}>
                  <MaterialIcons name="gavel" size={16} color={colors.onSurfaceVariant} />
                  <Text style={styles.ruleText}>
                    Statutory Rule: {item.applicable_rule_code}
                  </Text>
                </View>
              ) : null}

              {/* Inspector Status & Adjudication */}
              <View style={styles.adjudicationFooter}>
                <View style={styles.statusCol}>
                  <Text style={styles.statusLabel}>Inspector Adjudication:</Text>
                  <Text style={styles.statusValue}>
                    {item.inspector_status === 'PENDING_REVIEW'
                      ? 'Needs Inspector Verification'
                      : item.inspector_status.replace(/_/g, ' ')}
                  </Text>
                  {item.inspector_remarks ? (
                    <Text style={styles.remarksText}>Note: {item.inspector_remarks}</Text>
                  ) : null}
                </View>

                <TouchableOpacity
                  style={styles.adjudicateBtn}
                  onPress={() => openAdjudicationModal(item)}
                >
                  <Text style={styles.adjudicateBtnText}>Adjudicate</Text>
                  <MaterialIcons name="edit" size={16} color={colors.primary} />
                </TouchableOpacity>
              </View>
            </View>
          );
        })}

        {/* Action Buttons */}
        <View style={styles.bottomActions}>
          <TouchableOpacity
            style={styles.secondaryBtn}
            onPress={handleRerunComparison}
            disabled={comparing}
          >
            {comparing ? (
              <ActivityIndicator size="small" color={colors.primary} />
            ) : (
              <>
                <MaterialIcons name="sync" size={18} color={colors.primary} />
                <Text style={styles.secondaryBtnText}>Re-run Comparison</Text>
              </>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.primaryBtn}
            onPress={() => navigation.navigate('Findings', { inspectionId, inspectionNumber })}
          >
            <Text style={styles.primaryBtnText}>Continue to Statutory Findings →</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>

      {/* Adjudication Modal */}
      <Modal visible={!!activeItem} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>
              Adjudicate {activeItem ? formatFieldName(activeItem.field_name) : ''}
            </Text>
            <Text style={styles.modalSub}>
              Inspector maintains final authority over legal compliance findings.
            </Text>

            {/* Outcome Selection */}
            <View style={styles.outcomeSelector}>
              <TouchableOpacity
                style={[
                  styles.outcomeBtn,
                  adjudicationOutcome === 'CONFIRMED_DISCREPANCY' && styles.outcomeBtnActiveConflict,
                ]}
                onPress={() => setAdjudicationOutcome('CONFIRMED_DISCREPANCY')}
              >
                <Text
                  style={[
                    styles.outcomeBtnText,
                    adjudicationOutcome === 'CONFIRMED_DISCREPANCY' && styles.outcomeBtnTextActive,
                  ]}
                >
                  Confirm Discrepancy
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[
                  styles.outcomeBtn,
                  adjudicationOutcome === 'VERIFIED_MATCH' && styles.outcomeBtnActiveMatch,
                ]}
                onPress={() => setAdjudicationOutcome('VERIFIED_MATCH')}
              >
                <Text
                  style={[
                    styles.outcomeBtnText,
                    adjudicationOutcome === 'VERIFIED_MATCH' && styles.outcomeBtnTextActive,
                  ]}
                >
                  Verify Match
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[
                  styles.outcomeBtn,
                  adjudicationOutcome === 'DISMISSED_DISCREPANCY' && styles.outcomeBtnActiveDismiss,
                ]}
                onPress={() => setAdjudicationOutcome('DISMISSED_DISCREPANCY')}
              >
                <Text
                  style={[
                    styles.outcomeBtnText,
                    adjudicationOutcome === 'DISMISSED_DISCREPANCY' && styles.outcomeBtnTextActive,
                  ]}
                >
                  Dismiss Discrepancy
                </Text>
              </TouchableOpacity>
            </View>

            {/* Remarks Input */}
            <Text style={styles.inputLabel}>Inspector Justification Remarks:</Text>
            <TextInput
              style={styles.textArea}
              multiline
              numberOfLines={3}
              placeholder="Provide statutory justification or observation notes..."
              placeholderTextColor="#9ca3af"
              value={inspectorNotes}
              onChangeText={setInspectorNotes}
            />

            <View style={styles.modalActions}>
              <TouchableOpacity
                style={styles.modalCancelBtn}
                onPress={() => setActiveItem(null)}
              >
                <Text style={styles.modalCancelBtnText}>Cancel</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.modalSaveBtn}
                onPress={submitAdjudication}
                disabled={savingAdjudication}
              >
                {savingAdjudication ? (
                  <ActivityIndicator size="small" color="#fff" />
                ) : (
                  <Text style={styles.modalSaveBtnText}>Save Finding</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      <BottomNav />
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#f8fafc',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.gutter,
  },
  loadingText: {
    marginTop: spacing.stackMd,
    ...typography.bodyMd,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.gutter,
    paddingVertical: spacing.stackMd,
    backgroundColor: '#ffffff',
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
  },
  backButton: {
    padding: spacing.tight,
  },
  headerTitles: {
    flex: 1,
    marginLeft: spacing.tight,
  },
  headerTitle: {
    ...typography.sectionHeader,
    fontSize: 18,
    color: colors.primary,
  },
  headerSubtitle: {
    ...typography.caption,
    color: colors.onSurfaceVariant,
  },
  scrollView: {
    flex: 1,
  },
  contentContainer: {
    padding: spacing.stackMd,
    paddingBottom: 100,
  },
  summaryBar: {
    flexDirection: 'row',
    backgroundColor: '#ffffff',
    borderRadius: borderRadius.lg,
    padding: spacing.stackMd,
    marginBottom: spacing.stackMd,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    justifyContent: 'space-around',
    alignItems: 'center',
  },
  summaryChip: {
    alignItems: 'center',
    flex: 1,
  },
  summaryCount: {
    fontSize: 22,
    fontWeight: '700',
  },
  summaryLabel: {
    fontSize: 11,
    color: colors.onSurfaceVariant,
    marginTop: 2,
    textAlign: 'center',
  },
  summaryDivider: {
    width: 1,
    height: 30,
    backgroundColor: '#e2e8f0',
  },
  tableCard: {
    backgroundColor: '#ffffff',
    borderRadius: borderRadius.lg,
    padding: spacing.stackMd,
    marginBottom: spacing.gutter,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  cardSectionTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.onSurface,
    letterSpacing: 0.5,
  },
  cardSectionSub: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    marginBottom: spacing.stackMd,
    marginTop: 2,
  },
  tableBody: {
    borderTopWidth: 1,
    borderTopColor: '#f1f5f9',
  },
  tableRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#f1f5f9',
  },
  tableField: {
    fontSize: 14,
    fontWeight: '500',
    color: colors.onSurface,
  },
  badge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  badgeText: {
    fontSize: 12,
    fontWeight: '600',
  },
  sectionHeader: {
    ...typography.sectionHeader,
    fontSize: 16,
    color: colors.onSurface,
    marginBottom: spacing.tight,
  },
  itemCard: {
    backgroundColor: '#ffffff',
    borderRadius: borderRadius.lg,
    padding: spacing.stackMd,
    marginBottom: spacing.stackMd,
    borderWidth: 1,
  },
  itemCardMatch: {
    borderColor: '#e2e8f0',
  },
  itemCardConflict: {
    borderColor: '#fca5a5',
    backgroundColor: '#fffcfc',
  },
  itemCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.tight,
  },
  itemTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  itemFieldName: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.onSurface,
  },
  comparisonBox: {
    flexDirection: 'row',
    backgroundColor: '#f8fafc',
    borderRadius: borderRadius.sm,
    padding: spacing.tight,
    marginVertical: 6,
  },
  valueColumn: {
    flex: 1,
    paddingHorizontal: 4,
  },
  verticalDivider: {
    width: 1,
    backgroundColor: '#e2e8f0',
    marginHorizontal: 4,
  },
  valueLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: colors.onSurfaceVariant,
    marginBottom: 2,
    letterSpacing: 0.5,
  },
  valueText: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.onSurface,
  },
  provenanceTag: {
    fontSize: 9,
    color: '#64748b',
    marginTop: 4,
  },
  explanationBox: {
    backgroundColor: '#f1f5f9',
    borderRadius: borderRadius.sm,
    padding: 8,
    marginVertical: 6,
  },
  explanationText: {
    fontSize: 12,
    color: '#334155',
    lineHeight: 16,
  },
  evidenceSnippetBox: {
    marginVertical: 4,
  },
  evidenceSnippetLabel: {
    fontSize: 10,
    color: colors.onSurfaceVariant,
    fontWeight: '600',
  },
  evidenceSnippetText: {
    fontSize: 12,
    fontStyle: 'italic',
    color: '#475569',
  },
  ruleBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginVertical: 6,
    paddingVertical: 4,
  },
  ruleText: {
    fontSize: 11,
    color: colors.onSurfaceVariant,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  },
  adjudicationFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderTopWidth: 1,
    borderTopColor: '#f1f5f9',
    paddingTop: 8,
    marginTop: 6,
  },
  statusCol: {
    flex: 1,
  },
  statusLabel: {
    fontSize: 10,
    color: colors.onSurfaceVariant,
  },
  statusValue: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.onSurface,
  },
  remarksText: {
    fontSize: 11,
    color: '#64748b',
    fontStyle: 'italic',
  },
  adjudicateBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: colors.primary,
  },
  adjudicateBtnText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.primary,
  },
  bottomActions: {
    marginTop: spacing.gutter,
    gap: spacing.tight,
  },
  primaryBtn: {
    backgroundColor: colors.primary,
    paddingVertical: 14,
    borderRadius: borderRadius.lg,
    alignItems: 'center',
  },
  primaryBtnText: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '700',
  },
  secondaryBtn: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 12,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.primary,
    backgroundColor: '#ffffff',
  },
  secondaryBtnText: {
    color: colors.primary,
    fontSize: 14,
    fontWeight: '600',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  modalCard: {
    backgroundColor: '#ffffff',
    borderTopLeftRadius: borderRadius.xl,
    borderTopRightRadius: borderRadius.xl,
    padding: spacing.gutter,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.onSurface,
  },
  modalSub: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    marginBottom: spacing.stackMd,
  },
  outcomeSelector: {
    flexDirection: 'column',
    gap: 8,
    marginBottom: spacing.stackMd,
  },
  outcomeBtn: {
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: '#cbd5e1',
    alignItems: 'center',
  },
  outcomeBtnActiveConflict: {
    backgroundColor: '#dc2626',
    borderColor: '#dc2626',
  },
  outcomeBtnActiveMatch: {
    backgroundColor: '#16a34a',
    borderColor: '#16a34a',
  },
  outcomeBtnActiveDismiss: {
    backgroundColor: '#64748b',
    borderColor: '#64748b',
  },
  outcomeBtnText: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.onSurface,
  },
  outcomeBtnTextActive: {
    color: '#ffffff',
  },
  inputLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.onSurface,
    marginBottom: 4,
  },
  textArea: {
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: borderRadius.sm,
    padding: 10,
    fontSize: 13,
    textAlignVertical: 'top',
    marginBottom: spacing.gutter,
  },
  modalActions: {
    flexDirection: 'row',
    gap: spacing.stackMd,
  },
  modalCancelBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: borderRadius.lg,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#cbd5e1',
  },
  modalCancelBtnText: {
    fontSize: 14,
    color: colors.onSurfaceVariant,
    fontWeight: '600',
  },
  modalSaveBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: borderRadius.lg,
    alignItems: 'center',
    backgroundColor: colors.primary,
  },
  modalSaveBtnText: {
    fontSize: 14,
    color: '#ffffff',
    fontWeight: '700',
  },
});
