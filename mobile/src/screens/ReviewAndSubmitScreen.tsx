import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  TextInput,
  Alert,
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { AppHeader } from '../components/AppHeader';
import { StatusBadge } from '../components/StatusBadge';
import { api } from '../services/api';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const ReviewAndSubmitScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'ReviewAndSubmit'>>();
  const { inspectionId, inspectionNumber } = route.params;

  const [inspection, setInspection] = useState<any | null>(null);
  const [declarations, setDeclarations] = useState<any[]>([]);
  const [findings, setFindings] = useState<any[]>([]);
  const [officerNotes, setOfficerNotes] = useState('Finalized by Inspecting Officer after human adjudication.');
  const [loading, setLoading] = useState(true);
  const [finalizing, setFinalizing] = useState(false);

  useEffect(() => {
    const loadAll = async () => {
      try {
        const [insp, decls, fnds] = await Promise.all([
          api.getInspection(inspectionId),
          api.getDeclarations(inspectionId),
          api.getFindings(inspectionId),
        ]);
        setInspection(insp);
        setDeclarations(decls);
        setFindings(fnds);
      } catch (err) {
        console.error('Failed to load review summary:', err);
      } finally {
        setLoading(false);
      }
    };

    loadAll();
  }, [inspectionId]);

  const handleFinalize = async () => {
    setFinalizing(true);
    try {
      await api.finalizeInspection(inspectionId, {
        officer_notes: officerNotes.trim(),
      });

      navigation.replace('ReportPreview', {
        inspectionId,
        inspectionNumber: inspection?.inspection_number || inspectionNumber,
      });
    } catch (err: any) {
      Alert.alert('Finalization Error', err.message || 'Could not finalize inspection.');
    } finally {
      setFinalizing(false);
    }
  };

  const passCount = findings.filter((f) => f.result_state === 'PASS').length;
  const nonCompCount = findings.filter((f) => f.result_state === 'POTENTIAL_NON_COMPLIANCE').length;
  const insufficientCount = findings.filter((f) => f.result_state === 'INSUFFICIENT_EVIDENCE').length;

  const resolvedActions = new Set(['CONFIRMED', 'DISMISSED', 'NOT_APPLICABLE', 'CORRECTED']);
  const unresolvedFindings = findings.filter(
    (f) => f.result_state !== 'PASS' && !resolvedActions.has(f.adjudication_status)
  );
  const unresolvedCount = unresolvedFindings.length;

  const overallStatus = inspection?.overall_status;
  const isNoViolations = overallStatus === 'NO_POTENTIAL_VIOLATIONS';

  return (
    <View style={styles.container}>
      <AppHeader
        title="REVIEW & SUBMIT"
        subtitle={`Final Summary: ${inspection?.inspection_number || inspectionNumber || 'LM-2026'}`}
        showBack={true}
        onBackPress={() => navigation.goBack()}
      />

      <ScrollView contentContainerStyle={styles.scrollContent}>
        {loading ? (
          <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
        ) : (
          <>
            {/* Commodity Summary Card */}
            <View style={styles.card}>
              <View style={styles.cardHeader}>
                <Text style={typography.sectionHeader}>Packaged Commodity Details</Text>
                <StatusBadge status={inspection?.overall_status || 'PENDING_REVIEW'} />
              </View>

              <View style={styles.specGrid}>
                <View style={styles.specRow}>
                  <Text style={styles.specLabel}>Commodity:</Text>
                  <Text style={styles.specValueBold}>
                    {inspection?.product?.product_name || 'Packaged Commodity'}
                  </Text>
                </View>

                <View style={styles.specRow}>
                  <Text style={styles.specLabel}>Brand / Trademark:</Text>
                  <Text style={styles.specValue}>
                    {inspection?.product?.brand_name || 'N/A'}
                  </Text>
                </View>

                <View style={styles.specRow}>
                  <Text style={styles.specLabel}>Category:</Text>
                  <Text style={styles.specValue}>
                    {inspection?.product?.category || 'Packaged Food'}
                  </Text>
                </View>

                <View style={styles.specRow}>
                  <Text style={styles.specLabel}>Batch Number:</Text>
                  <Text style={styles.specValue}>
                    {inspection?.product?.batch_number || 'N/A'}
                  </Text>
                </View>

                <View style={styles.specRow}>
                  <Text style={styles.specLabel}>Inspection Site:</Text>
                  <Text style={styles.specValue}>{inspection?.location || 'Field Location'}</Text>
                </View>
              </View>
            </View>

            {/* Compliance Evaluation Metrics Card */}
            <View style={styles.card}>
              <Text style={typography.sectionHeader}>Rule Engine Evaluation Summary</Text>
              <View style={styles.metricsSummaryRow}>
                <View style={[styles.miniMetric, { backgroundColor: colors.statusGreenBg, borderColor: colors.statusGreenText }]}>
                  <Text style={[styles.miniMetricCount, { color: colors.statusGreenText }]}>{passCount}</Text>
                  <Text style={[styles.miniMetricLabel, { color: colors.statusGreenText }]}>PASS</Text>
                </View>

                <View style={[styles.miniMetric, { backgroundColor: colors.statusRedBg, borderColor: colors.statusRedText }]}>
                  <Text style={[styles.miniMetricCount, { color: colors.statusRedText }]}>{nonCompCount}</Text>
                  <Text style={[styles.miniMetricLabel, { color: colors.statusRedText }]}>POTENTIAL NON-COMPLIANCE</Text>
                </View>

                <View style={[styles.miniMetric, { backgroundColor: colors.statusAmberBg, borderColor: colors.statusAmberText }]}>
                  <Text style={[styles.miniMetricCount, { color: colors.statusAmberText }]}>{insufficientCount}</Text>
                  <Text style={[styles.miniMetricLabel, { color: colors.statusAmberText }]}>INSUFFICIENT</Text>
                </View>
              </View>
            </View>

            {/* Statutory Declarations Snapshot */}
            <View style={styles.card}>
              <Text style={typography.sectionHeader}>Verified Declarations Audit</Text>
              {declarations.map((d, i) => (
                <View key={d.id || i} style={styles.declSummaryRow}>
                  <Text style={styles.declFieldName}>
                    {d.field_name.replace(/_/g, ' ').toUpperCase()}
                  </Text>
                  <Text style={styles.declFieldValue} numberOfLines={1}>
                    {d.effective_value || 'None'}
                  </Text>
                </View>
              ))}
            </View>

            {/* Final Officer Notes */}
            <View style={styles.card}>
              <Text style={typography.labelCaps}>Inspecting Officer Final Remarks</Text>
              <TextInput
                style={styles.notesInput}
                value={officerNotes}
                onChangeText={setOfficerNotes}
                placeholder="Enter final inspection remarks..."
                placeholderTextColor={colors.outline}
                multiline
                numberOfLines={3}
              />
            </View>

            {/* Unresolved Findings Warning */}
            {unresolvedCount > 0 && (
              <View style={styles.unresolvedCard}>
                <MaterialIcons name="warning" size={20} color={colors.statusAmberText} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.unresolvedTitle}>
                    {unresolvedCount} Finding{unresolvedCount > 1 ? 's' : ''} Require Adjudication
                  </Text>
                  <Text style={styles.unresolvedBody}>
                    Return to Findings and adjudicate each finding (Confirm / Dismiss / Correct / Mark N/A) before the report can be generated.
                  </Text>
                </View>
              </View>
            )}

            {/* Legal Disclaimer Card — shown when no violations detected */}
            {isNoViolations && (
              <View style={styles.disclaimerCard}>
                <MaterialIcons name="info" size={18} color={colors.primary} />
                <Text style={styles.disclaimerText}>
                  The implemented machine-verifiable checks did not identify a potential issue based on the available evidence. This is not a certification of full legal compliance.
                </Text>
              </View>
            )}

            {/* Submit & Generate Report Button */}
            <TouchableOpacity
              style={[
                styles.finalizeButton,
                unresolvedCount > 0 && styles.finalizeButtonDisabled,
              ]}
              onPress={() => {
                if (unresolvedCount > 0) {
                  Alert.alert(
                    'Unresolved Findings',
                    `${unresolvedCount} finding${unresolvedCount > 1 ? 's' : ''} must be adjudicated before the inspection can be finalized. Return to Findings.`
                  );
                  return;
                }
                handleFinalize();
              }}
              disabled={finalizing}
              activeOpacity={0.85}
            >
              {finalizing ? (
                <ActivityIndicator size="small" color={colors.onPrimary} />
              ) : (
                <View style={styles.btnInner}>
                  <Text style={styles.finalizeButtonText}>
                    {unresolvedCount > 0
                      ? `${unresolvedCount} Finding${unresolvedCount > 1 ? 's' : ''} Need Adjudication`
                      : 'Submit & Generate Statutory Report'}
                  </Text>
                  <MaterialIcons
                    name={unresolvedCount > 0 ? 'warning' : 'picture-as-pdf'}
                    size={18}
                    color={colors.onPrimary}
                  />
                </View>
              )}
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
  card: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.marginX,
    gap: spacing.stackSm,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  specGrid: {
    gap: 6,
    marginTop: 4,
  },
  specRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  specLabel: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.onSurfaceVariant,
    width: 130,
  },
  specValue: {
    ...typography.bodySm,
    color: colors.onSurface,
    flex: 1,
  },
  specValueBold: {
    ...typography.bodyMdMedium,
    color: colors.primary,
    flex: 1,
  },
  metricsSummaryRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 4,
  },
  miniMetric: {
    flex: 1,
    borderWidth: 1,
    borderRadius: borderRadius.sm,
    padding: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  miniMetricCount: {
    ...typography.headlineLg,
    fontSize: 18,
    lineHeight: 22,
  },
  miniMetricLabel: {
    ...typography.caption,
    fontSize: 9,
    fontWeight: '700',
    textAlign: 'center',
    marginTop: 2,
  },
  declSummaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 4,
    borderBottomWidth: 1,
    borderBottomColor: colors.surfaceContainerHigh,
  },
  declFieldName: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
    flex: 1,
  },
  declFieldValue: {
    ...typography.bodySm,
    fontWeight: '600',
    color: colors.primary,
    maxWidth: 180,
    textAlign: 'right',
  },
  notesInput: {
    backgroundColor: colors.surfaceBright,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    paddingHorizontal: 12,
    paddingVertical: 8,
    ...typography.bodyMd,
    color: colors.onSurface,
    minHeight: 64,
    textAlignVertical: 'top',
  },
  finalizeButton: {
    backgroundColor: colors.primary,
    paddingVertical: 12,
    borderRadius: borderRadius.lg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  finalizeButtonDisabled: {
    backgroundColor: colors.statusAmberText,
  },
  btnInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  finalizeButtonText: {
    ...typography.sectionHeader,
    color: colors.onPrimary,
  },
  unresolvedCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    padding: spacing.stackMd,
    backgroundColor: colors.statusAmberBg,
    borderWidth: 1,
    borderColor: colors.statusAmberText,
    borderRadius: borderRadius.lg,
  },
  unresolvedTitle: {
    ...typography.bodySm,
    fontWeight: '700',
    color: colors.statusAmberText,
    marginBottom: 2,
  },
  unresolvedBody: {
    ...typography.caption,
    color: colors.onSurface,
    lineHeight: 16,
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
