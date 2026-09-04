import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  Image,
  ActivityIndicator,
  TouchableOpacity,
  TextInput,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { ProfileAvatar } from '../components/ProfileAvatar';
import { api, getApiBaseUrl } from '../services/api';
import { authStorage } from '../services/authStorage';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const EvidenceReviewScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'EvidenceReview'>>();
  const { inspectionId, findingId } = route.params;

  const [images, setImages] = useState<any[]>([]);
  const [finding, setFinding] = useState<any | null>(null);
  const [profile, setProfile] = useState<any | null>(null);
  const [remarks, setRemarks] = useState('');
  const [loading, setLoading] = useState(true);
  const [savingDecision, setSavingDecision] = useState(false);

  useEffect(() => {
    const loadEvidence = async () => {
      try {
        const [imgs, fnd, prof] = await Promise.all([
          api.getInspectionImages(inspectionId),
          findingId ? api.getFinding(findingId) : Promise.resolve(null),
          authStorage.getProfile(),
        ]);
        setImages(imgs || []);
        setFinding(fnd);
        setProfile(prof);
      } catch (err) {
        console.error('Failed to load evidence details:', err);
      } finally {
        setLoading(false);
      }
    };

    loadEvidence();
  }, [inspectionId, findingId]);

  const handleDecision = async (action: 'CONFIRMED' | 'DISMISSED' | 'NOT_APPLICABLE' | 'CORRECTED') => {
    if (!findingId) {
      navigation.goBack();
      return;
    }

    setSavingDecision(true);
    try {
      await api.adjudicateFinding(findingId, {
        action,
        notes: remarks.trim() || undefined,
      });
      Alert.alert('Decision Saved', `Finding marked as ${action}.`, [
        {
          text: 'OK',
          onPress: () => navigation.goBack(),
        },
      ]);
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Could not record finding decision.');
    } finally {
      setSavingDecision(false);
    }
  };

  const baseUrl = getApiBaseUrl();
  const primaryImage = images.length > 0 ? images[0] : null;

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        {/* Stitch TopAppBar Header */}
        <View style={styles.topHeader}>
          <TouchableOpacity
            style={styles.backButton}
            onPress={() => navigation.goBack()}
            activeOpacity={0.7}
          >
            <MaterialIcons name="arrow-back" size={24} color={colors.primary} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Evidence Review</Text>
          <ProfileAvatar size={36} />
        </View>

        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          {loading ? (
            <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
          ) : (
            <>
              {/* Finding Summary Banner */}
              <View style={styles.summaryCard}>
                <View style={styles.summaryTopRow}>
                  <Text style={styles.summaryHeading}>Finding Summary</Text>
                  <View style={styles.badgeAmber}>
                    <Text style={styles.badgeAmberText}>Potential Non-Compliance</Text>
                  </View>
                </View>
                <Text style={styles.findingTitleText}>
                  {finding ? finding.title : 'MRP Declaration Requires Verification'}
                </Text>
              </View>

              {/* Photo Viewer with Bounding Box overlay */}
              <View style={styles.photoContainer}>
                {primaryImage ? (
                  <Image
                    source={{ uri: `${baseUrl}${primaryImage.file_path}` }}
                    style={styles.photoImage}
                    resizeMode="cover"
                  />
                ) : (
                  <View style={styles.placeholderPhoto}>
                    <MaterialIcons name="image" size={48} color={colors.secondary} />
                    <Text style={styles.placeholderText}>Package Evidence Photo</Text>
                  </View>
                )}

                {/* Overlay Bounding Box */}
                <View style={styles.overlayBoundingBox} />

                {/* Zoom Controls Bar */}
                <View style={styles.zoomControls}>
                  <TouchableOpacity style={styles.zoomBtn}>
                    <MaterialIcons name="zoom-out" size={20} color={colors.onSurface} />
                  </TouchableOpacity>
                  <TouchableOpacity style={[styles.zoomBtn, styles.zoomBtnBorder]}>
                    <MaterialIcons name="zoom-in" size={20} color={colors.onSurface} />
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.zoomBtn}>
                    <MaterialIcons name="pan-tool" size={20} color={colors.onSurface} />
                  </TouchableOpacity>
                </View>
              </View>

              {/* Crop Fallback Box */}
              <View style={styles.cropFallbackBox}>
                <View style={styles.cropHeader}>
                  <MaterialIcons name="attachment" size={16} color={colors.onSurfaceVariant} />
                  <Text style={styles.cropHeaderText}>Evidence Crop Unavailable — fallback shown</Text>
                </View>
                <Text style={styles.cropBodyText}>
                  A precise bounding-box crop could not be generated for this field. Full source image is displayed as fallback per inspection protocol.
                </Text>
                <TouchableOpacity style={styles.viewFullImageBtn}>
                  <Text style={styles.viewFullImageText}>[ View Full Image ]</Text>
                </TouchableOpacity>
              </View>

              {/* Metadata row */}
              <View style={styles.metaRow}>
                <Text style={styles.metaText}>Inspection ID: {finding?.rule_code || 'LM-2026-00891'}</Text>
                <Text style={styles.metaText}>Inspector: {profile?.full_name || 'Rajesh Kumar'}</Text>
              </View>

              {/* Why was this flagged? Card */}
              <View style={styles.infoCard}>
                <Text style={styles.infoCardLabel}>Why was this flagged?</Text>
                <Text style={styles.infoCardValue}>
                  {finding ? finding.explanation || finding.description : 'The MRP declaration could not be reliably read from the provided image. Further verification by the authorized inspector is required.'}
                </Text>
              </View>

              {/* Rule Reference Card */}
              <View style={styles.infoCard}>
                <Text style={styles.infoCardLabel}>Rule Reference</Text>
                <View style={styles.ruleContentRow}>
                  <MaterialIcons name="gavel" size={20} color={colors.primary} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.ruleTitle}>Legal Metrology (Packaged Commodities) Rules, 2011</Text>
                    <Text style={styles.ruleSub}>Rule Version: v1.0 • Rule: {finding?.rule_code || 'LM-RULE-002'}</Text>
                  </View>
                </View>
              </View>

              {/* OCR Analysis & Audit Card */}
              <View style={styles.auditCard}>
                <View style={styles.auditHeader}>
                  <MaterialIcons name="document-scanner" size={16} color={colors.onSurfaceVariant} />
                  <Text style={styles.auditHeaderText}>OCR Analysis & Audit</Text>
                </View>

                <View style={styles.auditItemRow}>
                  <Text style={styles.auditLabel}>AI Extracted Value</Text>
                  <Text style={styles.auditValue}>
                    {finding?.extracted_value || finding?.effective_value || '—'}
                  </Text>
                </View>
                <View style={styles.auditItemRow}>
                  <Text style={styles.auditLabel}>Inspector Corrected Value</Text>
                  <Text style={[styles.auditValue, { fontWeight: '700' }]}>
                    {finding?.adjudication_notes || finding?.effective_value || '—'}
                  </Text>
                </View>
                <View style={styles.auditItemRow}>
                  <Text style={styles.auditLabel}>Corrected By</Text>
                  <Text style={styles.auditValue}>{profile?.full_name || profile?.officer_id || '—'}</Text>
                </View>
                <View style={styles.auditItemRow}>
                  <Text style={styles.auditLabel}>OCR Confidence</Text>
                  <Text style={[
                    styles.auditValue,
                    {
                      color: finding?.confidence != null && finding.confidence < 0.7
                        ? colors.statusRedText
                        : colors.statusGreenText,
                      fontWeight: '600'
                    }
                  ]}>
                    {finding?.confidence != null
                      ? `${finding.confidence < 0.7 ? 'Low' : finding.confidence < 0.9 ? 'Medium' : 'High'} — ${Math.round((finding.confidence || 0) * 100)}%`
                      : '—'}
                  </Text>
                </View>
                <View style={[styles.auditItemRow, { borderBottomWidth: 0 }]}>
                  <Text style={styles.auditLabel}>Timestamp</Text>
                  <Text style={styles.auditValue}>
                    {finding?.created_at
                      ? new Date(finding.created_at).toLocaleString('en-GB', {
                          day: 'numeric', month: 'short', year: 'numeric',
                          hour: '2-digit', minute: '2-digit'
                        })
                      : '—'}
                  </Text>
                </View>
              </View>

              {/* Inspector Remarks */}
              <View style={styles.remarksCard}>
                <Text style={styles.remarksLabel}>Inspector Remarks</Text>
                <TextInput
                  style={styles.remarksInput}
                  value={remarks}
                  onChangeText={setRemarks}
                  placeholder="Add notes about this finding..."
                  placeholderTextColor={colors.outline}
                  multiline
                  numberOfLines={2}
                />
              </View>

              {/* Decision Buttons */}
              <View style={styles.decisionsContainer}>
                <Text style={styles.decisionsTitle}>Inspector Decision</Text>

                <TouchableOpacity
                  style={styles.confirmDecisionBtn}
                  onPress={() => handleDecision('CONFIRMED')}
                  disabled={savingDecision}
                  activeOpacity={0.85}
                >
                  {savingDecision ? (
                    <ActivityIndicator size="small" color={colors.onPrimary} />
                  ) : (
                    <View style={styles.btnRow}>
                      <MaterialIcons name="check-circle" size={18} color={colors.onPrimary} />
                      <Text style={styles.confirmDecisionText}>Confirm Finding</Text>
                    </View>
                  )}
                </TouchableOpacity>
                <Text style={styles.confirmHelper}>
                  Records the inspector’s decision for this potential finding.
                </Text>

                <View style={styles.decisionGrid}>
                  <TouchableOpacity
                    style={styles.gridBtn}
                    onPress={() => handleDecision('DISMISSED')}
                    activeOpacity={0.8}
                  >
                    <MaterialIcons name="cancel" size={16} color={colors.statusRedText} />
                    <Text style={styles.gridBtnText}>Reject</Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    style={styles.gridBtn}
                    onPress={() => handleDecision('CORRECTED')}
                    activeOpacity={0.8}
                  >
                    <MaterialIcons name="edit-note" size={18} color={colors.primary} />
                    <Text style={styles.gridBtnText}>Correct Info</Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    style={styles.gridBtn}
                    onPress={() => {
                      if (finding) {
                        api.requestNewImage(finding.id);
                      }
                      navigation.navigate('CaptureImages', { inspectionId });
                    }}
                    activeOpacity={0.8}
                  >
                    <MaterialIcons name="add-a-photo" size={16} color={colors.primary} />
                    <Text style={styles.gridBtnText}>Request Image</Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    style={styles.gridBtn}
                    onPress={() => handleDecision('NOT_APPLICABLE')}
                    activeOpacity={0.8}
                  >
                    <MaterialIcons name="block" size={16} color={colors.secondary} />
                    <Text style={styles.gridBtnText}>N/A</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </>
          )}
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
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    backgroundColor: colors.surfaceContainerLow,
    alignItems: 'center',
    justifyContent: 'center',
  },
  scrollContent: {
    paddingHorizontal: spacing.gutter,
    paddingTop: spacing.stackMd,
    paddingBottom: 40,
    gap: spacing.stackMd,
  },
  summaryCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    padding: spacing.gutter,
    gap: 8,
  },
  summaryTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  summaryHeading: {
    ...typography.sectionHeader,
    fontSize: 16,
    lineHeight: 24,
    color: colors.onSurface,
  },
  badgeAmber: {
    backgroundColor: colors.statusAmberBg,
    borderWidth: 1,
    borderColor: colors.statusAmberText,
    borderRadius: borderRadius.DEFAULT,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  badgeAmberText: {
    ...typography.labelCaps,
    fontSize: 11,
    color: colors.statusAmberText,
    fontWeight: '600',
  },
  findingTitleText: {
    ...typography.bodyMd,
    fontSize: 14,
    fontWeight: '600',
    color: colors.onSurface,
  },
  photoContainer: {
    height: 240,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    backgroundColor: colors.surfaceContainerLow,
    position: 'relative',
    overflow: 'hidden',
  },
  photoImage: {
    width: '100%',
    height: '100%',
  },
  placeholderPhoto: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  placeholderText: {
    ...typography.bodySm,
    color: colors.secondary,
  },
  overlayBoundingBox: {
    position: 'absolute',
    top: '30%',
    left: '20%',
    width: 160,
    height: 90,
    borderWidth: 2,
    borderColor: colors.statusAmberText,
    backgroundColor: 'rgba(230, 81, 0, 0.08)',
  },
  zoomControls: {
    position: 'absolute',
    bottom: 12,
    right: 12,
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    elevation: 2,
  },
  zoomBtn: {
    padding: 6,
  },
  zoomBtnBorder: {
    borderLeftWidth: 1,
    borderRightWidth: 1,
    borderColor: colors.borderSubtle,
  },
  cropFallbackBox: {
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    padding: spacing.gutter,
    gap: 8,
  },
  cropHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  cropHeaderText: {
    ...typography.labelCaps,
    fontSize: 11,
    color: colors.onSurfaceVariant,
    fontWeight: '600',
  },
  cropBodyText: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.onSurface,
  },
  viewFullImageBtn: {
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    backgroundColor: colors.surface,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: borderRadius.DEFAULT,
  },
  viewFullImageText: {
    ...typography.labelCaps,
    fontSize: 12,
    color: colors.primary,
    fontWeight: '600',
  },
  metaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 4,
  },
  metaText: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
  },
  infoCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    padding: spacing.gutter,
    gap: 6,
  },
  infoCardLabel: {
    ...typography.labelCaps,
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
  infoCardValue: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.onSurface,
  },
  ruleContentRow: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'flex-start',
  },
  ruleTitle: {
    ...typography.bodyMd,
    fontSize: 14,
    fontWeight: '600',
    color: colors.onSurface,
  },
  ruleSub: {
    ...typography.bodySm,
    fontSize: 12,
    color: colors.onSurfaceVariant,
    marginTop: 2,
  },
  auditCard: {
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    padding: spacing.gutter,
    gap: 8,
  },
  auditHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 4,
  },
  auditHeaderText: {
    ...typography.labelCaps,
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
  auditItemRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  auditLabel: {
    ...typography.bodySm,
    fontSize: 13,
    color: colors.onSurface,
  },
  auditValue: {
    ...typography.bodySm,
    fontSize: 13,
    color: colors.onSurface,
  },
  remarksCard: {
    gap: 6,
  },
  remarksLabel: {
    ...typography.labelCaps,
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
  remarksInput: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    padding: spacing.base,
    ...typography.bodySm,
    color: colors.onSurface,
    minHeight: 56,
  },
  decisionsContainer: {
    gap: 8,
    marginTop: 4,
  },
  decisionsTitle: {
    ...typography.labelCaps,
    fontSize: 12,
    color: colors.onSurfaceVariant,
  },
  confirmDecisionBtn: {
    backgroundColor: colors.primaryContainer,
    paddingVertical: 12,
    borderRadius: borderRadius.DEFAULT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  confirmDecisionText: {
    ...typography.sectionHeader,
    fontSize: 15,
    color: colors.onPrimary,
    fontWeight: '600',
  },
  confirmHelper: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
    marginBottom: 4,
  },
  decisionGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  gridBtn: {
    flex: 1,
    minWidth: '45%',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    gap: 6,
  },
  gridBtnText: {
    ...typography.bodyMd,
    fontSize: 13,
    color: colors.onSurface,
    fontWeight: '500',
  },
});

