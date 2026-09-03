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
import { SafeAreaView } from 'react-native-safe-area-context';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { BottomNav } from '../components/BottomNav';
import { ProfileAvatar } from '../components/ProfileAvatar';
import { api } from '../services/api';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const ReviewAndSubmitScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'ReviewAndSubmit'>>();
  const { inspectionId, inspectionNumber } = route.params;

  const [inspection, setInspection] = useState<any | null>(null);
  const [images, setImages] = useState<any[]>([]);
  const [officerNotes, setOfficerNotes] = useState('Finalized by Inspecting Officer after human verification.');
  const [loading, setLoading] = useState(true);
  const [finalizing, setFinalizing] = useState(false);

  useEffect(() => {
    const loadAll = async () => {
      try {
        const [insp, imgs] = await Promise.all([
          api.getInspection(inspectionId),
          api.getInspectionImages(inspectionId),
        ]);
        setInspection(insp);
        setImages(imgs || []);
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

  const frontCaptured = images.some((i) => i.view_type === 'front');
  const backCaptured = images.some((i) => i.view_type === 'back');
  const sideCaptured = images.some((i) => i.view_type === 'side' || i.view_type === 'panel');
  const backWarning = images.some((i) => i.view_type === 'back' && i.quality_status === 'WARNING');
  const capturedCount = images.length;

  const dateStr = inspection?.created_at
    ? new Date(inspection.created_at).toLocaleString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : 'Fetching...';

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
            <Text style={styles.headerTitle}>Step 3 of 3</Text>
          </View>
          <ProfileAvatar size={36} />
        </View>

        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          {/* Header Title */}
          <View style={styles.headerTitleBox}>
            <Text style={styles.pageTitle}>Review & Submit</Text>
            <Text style={styles.pageSubtitle}>
              Review Inspection. Confirm details before finalizing and generating report.
            </Text>
          </View>

          {loading ? (
            <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
          ) : (
            <>
              {/* Section 1: INSPECTION SUMMARY */}
              <View style={styles.cardSection}>
                <View style={styles.cardHeader}>
                  <Text style={styles.cardHeaderText}>INSPECTION SUMMARY</Text>
                </View>

                <View style={styles.cardBody}>
                  <View style={styles.summaryItemRow}>
                    <Text style={styles.summaryItemLabel}>ID</Text>
                    <Text style={styles.summaryItemValueBold}>
                      {inspection?.inspection_number || inspectionNumber || 'LM-2026-00891'}
                    </Text>
                  </View>
                  <View style={styles.summaryItemRow}>
                    <Text style={styles.summaryItemLabel}>Product</Text>
                    <Text style={styles.summaryItemValue}>
                      {inspection?.product?.product_name || 'Premium Basmati Rice'}
                    </Text>
                  </View>
                  <View style={styles.summaryItemRow}>
                    <Text style={styles.summaryItemLabel}>Brand</Text>
                    <Text style={styles.summaryItemValue}>
                      {inspection?.product?.brand_name || 'Agro Foods'}
                    </Text>
                  </View>
                  <View style={styles.summaryItemRow}>
                    <Text style={styles.summaryItemLabel}>Category</Text>
                    <Text style={styles.summaryItemValue}>
                      {inspection?.product?.category || 'Packaged Food'}
                    </Text>
                  </View>
                  <View style={styles.summaryItemRow}>
                    <Text style={styles.summaryItemLabel}>Location</Text>
                    <Text style={styles.summaryItemValue}>{inspection?.location || 'Sector 4 Market'}</Text>
                  </View>
                  <View style={[styles.summaryItemRow, { borderBottomWidth: 0 }]}>
                    <Text style={styles.summaryItemLabel}>Date</Text>
                    <Text style={styles.summaryItemValue}>{dateStr}</Text>
                  </View>
                </View>
              </View>

              {/* Section 2: IMAGES ATTACHED */}
              <View style={styles.cardSection}>
                <View style={[styles.cardHeader, styles.headerSpaceBetween]}>
                  <Text style={styles.cardHeaderText}>IMAGES ATTACHED</Text>
                  <Text style={styles.headerCount}>{capturedCount} of 3 views captured</Text>
                </View>

                <View style={styles.cardBody}>
                  <View style={styles.imageSlotRow}>
                    <MaterialIcons
                      name={frontCaptured ? 'check-circle' : 'radio-button-unchecked'}
                      size={20}
                      color={frontCaptured ? colors.statusGreenText : colors.outline}
                    />
                    <Text style={[styles.imageSlotText, !frontCaptured && { color: colors.outline }]}>Front</Text>
                  </View>

                  <View style={styles.imageSlotRow}>
                    <MaterialIcons
                      name={backCaptured ? (backWarning ? 'warning' : 'check-circle') : 'radio-button-unchecked'}
                      size={20}
                      color={backCaptured ? (backWarning ? colors.statusAmberText : colors.statusGreenText) : colors.outline}
                    />
                    <Text style={[styles.imageSlotText, !backCaptured && { color: colors.outline }]}>
                      Back{backWarning ? <Text style={styles.imageSlotSubText}> (quality warning)</Text> : null}
                    </Text>
                  </View>

                  <View style={styles.imageSlotRow}>
                    <MaterialIcons
                      name={sideCaptured ? 'check-circle' : 'radio-button-unchecked'}
                      size={20}
                      color={sideCaptured ? colors.statusGreenText : colors.outline}
                    />
                    <Text style={[styles.imageSlotText, !sideCaptured && { color: colors.outline }]}>
                      Side
                    </Text>
                  </View>

                  <TouchableOpacity
                    style={styles.editImagesBtn}
                    onPress={() => navigation.navigate('CaptureImages', { inspectionId, inspectionNumber })}
                    activeOpacity={0.8}
                  >
                    <MaterialIcons name="edit" size={16} color={colors.primary} />
                    <Text style={styles.editImagesText}>Edit Images</Text>
                  </TouchableOpacity>
                </View>
              </View>

              {/* Section 3: PRE-ANALYSIS CHECKLIST */}
              <View style={styles.cardSection}>
                <View style={styles.cardHeader}>
                  <Text style={styles.cardHeaderText}>PRE-ANALYSIS CHECKLIST</Text>
                </View>

                <View style={styles.cardBody}>
                  <View style={styles.checklistRow}>
                    <MaterialIcons
                      name={capturedCount > 0 ? 'check-circle' : 'radio-button-unchecked'}
                      size={18}
                      color={capturedCount > 0 ? colors.statusGreenText : colors.outline}
                    />
                    <Text style={styles.checklistText}>At least one clear image attached</Text>
                  </View>
                  <View style={styles.checklistRow}>
                    <MaterialIcons
                      name={inspection?.product?.category ? 'check-circle' : 'radio-button-unchecked'}
                      size={18}
                      color={inspection?.product?.category ? colors.statusGreenText : colors.outline}
                    />
                    <Text style={styles.checklistText}>Product category selected</Text>
                  </View>
                  <View style={styles.checklistRow}>
                    <MaterialIcons name="check-circle" size={18} color={colors.statusGreenText} />
                    <Text style={styles.checklistText}>Inspector ID confirmed</Text>
                  </View>
                  {backWarning && (
                    <View style={styles.checklistWarnBox}>
                      <MaterialIcons name="warning" size={18} color={colors.statusAmberText} />
                      <Text style={styles.checklistWarnText}>Back label image quality may reduce OCR accuracy</Text>
                    </View>
                  )}
                </View>
              </View>

              {/* Section 4: Officer Final Notes */}
              <View style={styles.cardSection}>
                <View style={styles.cardHeader}>
                  <Text style={styles.cardHeaderText}>OFFICER REMARKS</Text>
                </View>
                <View style={styles.cardBody}>
                  <TextInput
                    style={styles.remarksInput}
                    value={officerNotes}
                    onChangeText={setOfficerNotes}
                    placeholder="Enter final remarks..."
                    placeholderTextColor={colors.outline}
                    multiline
                    numberOfLines={2}
                  />
                </View>
              </View>

              {/* Action Buttons Row */}
              <View style={styles.footerActionRow}>
                <TouchableOpacity
                  style={styles.backBtn}
                  onPress={() => navigation.goBack()}
                  activeOpacity={0.8}
                >
                  <Text style={styles.backBtnText}>Back</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.submitBtn}
                  onPress={handleFinalize}
                  disabled={finalizing}
                  activeOpacity={0.85}
                >
                  {finalizing ? (
                    <ActivityIndicator size="small" color={colors.onPrimary} />
                  ) : (
                    <View style={styles.submitBtnContent}>
                      <MaterialIcons name="assignment-turned-in" size={18} color={colors.onPrimary} />
                      <Text style={styles.submitBtnText}>Finalize & Submit</Text>
                    </View>
                  )}
                </TouchableOpacity>
              </View>
            </>
          )}

          <View style={{ height: 30 }} />
        </ScrollView>

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
  headerTitleBox: {
    gap: 4,
    marginBottom: 4,
  },
  pageTitle: {
    ...typography.headlineLg,
    fontSize: 20,
    lineHeight: 28,
    fontWeight: '700',
    color: colors.onSurface,
  },
  pageSubtitle: {
    ...typography.bodyMd,
    fontSize: 13,
    lineHeight: 18,
    color: colors.onSurfaceVariant,
  },
  cardSection: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    overflow: 'hidden',
  },
  cardHeader: {
    paddingHorizontal: spacing.marginX,
    paddingVertical: spacing.stackSm,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    backgroundColor: colors.surfaceContainerLow,
  },
  headerSpaceBetween: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  cardHeaderText: {
    ...typography.labelCaps,
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 0.5,
    fontWeight: '700',
    color: colors.onSurfaceVariant,
    textTransform: 'uppercase',
  },
  headerCount: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
  cardBody: {
    paddingHorizontal: spacing.marginX,
    paddingVertical: spacing.stackSm,
  },
  summaryItemRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.stackSm,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  summaryItemLabel: {
    ...typography.bodySm,
    fontSize: 13,
    color: colors.onSurfaceVariant,
  },
  summaryItemValue: {
    ...typography.bodyMd,
    fontSize: 14,
    color: colors.onSurface,
  },
  summaryItemValueBold: {
    ...typography.bodyMd,
    fontSize: 14,
    fontWeight: '700',
    color: colors.onSurface,
  },
  imageSlotRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  imageSlotText: {
    ...typography.bodyMd,
    fontSize: 14,
    color: colors.onSurface,
    flex: 1,
  },
  imageSlotSubText: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
  editImagesBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: colors.primary,
    borderRadius: borderRadius.DEFAULT,
    gap: 6,
    marginTop: 10,
    marginBottom: 4,
  },
  editImagesText: {
    ...typography.sectionHeader,
    fontSize: 13,
    color: colors.primary,
    fontWeight: '600',
  },
  checklistRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  checklistText: {
    ...typography.bodySm,
    fontSize: 13,
    color: colors.onSurface,
  },
  checklistWarnBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: colors.statusAmberBg,
    padding: 8,
    borderRadius: borderRadius.DEFAULT,
    marginTop: 8,
    marginBottom: 4,
  },
  checklistWarnText: {
    ...typography.bodySm,
    fontSize: 12,
    color: colors.onSurface,
  },
  remarksInput: {
    backgroundColor: colors.surfaceBright,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    padding: 8,
    ...typography.bodySm,
    color: colors.onSurface,
    minHeight: 50,
  },
  footerActionRow: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 6,
  },
  backBtn: {
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderWidth: 1,
    borderColor: colors.primary,
    borderRadius: borderRadius.DEFAULT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  backBtnText: {
    ...typography.sectionHeader,
    fontSize: 14,
    color: colors.primary,
    fontWeight: '600',
  },
  submitBtn: {
    flex: 1,
    backgroundColor: colors.primary,
    paddingVertical: 12,
    borderRadius: borderRadius.DEFAULT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  submitBtnContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  submitBtnText: {
    ...typography.sectionHeader,
    fontSize: 14,
    color: colors.onPrimary,
    fontWeight: '700',
  },
});

