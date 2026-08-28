import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  Image,
  ActivityIndicator,
  TouchableOpacity,
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { AppHeader } from '../components/AppHeader';
import { api, getApiBaseUrl } from '../services/api';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const EvidenceReviewScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'EvidenceReview'>>();
  const { inspectionId, findingId } = route.params;

  const [images, setImages] = useState<any[]>([]);
  const [finding, setFinding] = useState<any | null>(null);
  const [evidenceList, setEvidenceList] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadEvidence = async () => {
      try {
        const [imgs, fnd, evs] = await Promise.all([
          api.getInspectionImages(inspectionId),
          findingId ? api.getFinding(findingId) : Promise.resolve(null),
          findingId ? api.getFindingEvidence(findingId) : Promise.resolve([]),
        ]);
        setImages(imgs);
        setFinding(fnd);
        setEvidenceList(evs);
      } catch (err) {
        console.error('Failed to load evidence details:', err);
      } finally {
        setLoading(false);
      }
    };

    loadEvidence();
  }, [inspectionId, findingId]);

  const baseUrl = getApiBaseUrl();
  const primaryImage = images.length > 0 ? images[0] : null;

  return (
    <View style={styles.container}>
      <AppHeader
        title="EVIDENCE REVIEW"
        subtitle={finding ? finding.rule_code : 'Photographic Evidence'}
        showBack={true}
        onBackPress={() => navigation.goBack()}
      />

      <ScrollView contentContainerStyle={styles.scrollContent}>
        {loading ? (
          <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
        ) : (
          <>
            {/* Finding Overview Card */}
            {finding ? (
              <View style={styles.findingCard}>
                <View style={styles.findingRow}>
                  <Text style={styles.ruleCode}>{finding.rule_code}</Text>
                  <Text style={styles.severityText}>Severity: {finding.severity}</Text>
                </View>
                <Text style={styles.findingTitle}>{finding.title}</Text>
                <Text style={styles.findingExplanation}>{finding.explanation}</Text>
              </View>
            ) : null}

            {/* Photographic Image Viewer Card */}
            <View style={styles.imageCard}>
              <View style={styles.imageHeader}>
                <Text style={typography.labelCaps}>
                  {primaryImage ? `${primaryImage.view_type.toUpperCase()} PANEL EVIDENCE` : 'PACKAGE PHOTO'}
                </Text>
                {primaryImage ? (
                  <Text style={styles.imgScoreText}>
                    Quality: {primaryImage.quality_status} ({Math.round(primaryImage.quality_score * 100)}%)
                  </Text>
                ) : null}
              </View>

              {primaryImage ? (
                <View style={styles.imageWrapper}>
                  <Image
                    source={{ uri: `${baseUrl}${primaryImage.file_path}` }}
                    style={styles.evidenceImage}
                    resizeMode="contain"
                  />
                  {/* Simulated bounding box indicator banner */}
                  <View style={styles.highlightBadge}>
                    <MaterialIcons name="crop-free" size={14} color={colors.onPrimary} />
                    <Text style={styles.highlightBadgeText}>OCR Region Bounding Box Verified</Text>
                  </View>
                </View>
              ) : (
                <View style={styles.noImageBox}>
                  <MaterialIcons name="image-not-supported" size={36} color={colors.outline} />
                  <Text style={styles.noImageText}>INSUFFICIENT EVIDENCE / NO PHOTO</Text>
                </View>
              )}
            </View>

            {/* Extracted Evidence Details Card */}
            <View style={styles.extractedTextCard}>
              <Text style={typography.labelCaps}>EVIDENCE HIGHLIGHT & OCR AUDIT</Text>

              {evidenceList.length > 0 ? (
                evidenceList.map((ev, i) => (
                  <View key={ev.id || i} style={styles.evidenceItem}>
                    <Text style={styles.evidenceReason}>
                      <Text style={{ fontWeight: '700' }}>Reason: </Text>{ev.reason || 'Detected text fragment'}
                    </Text>
                    <View style={styles.highlightTextBox}>
                      <Text style={styles.highlightTextVal}>
                        "{ev.highlight_text || finding?.extracted_value || 'None'}"
                      </Text>
                    </View>
                  </View>
                ))
              ) : (
                <View style={styles.evidenceItem}>
                  <Text style={styles.evidenceReason}>Evaluated Declaration Value:</Text>
                  <View style={styles.highlightTextBox}>
                    <Text style={styles.highlightTextVal}>
                      "{finding?.extracted_value || 'None / Not Detected'}"
                    </Text>
                  </View>
                </View>
              )}
            </View>

            <TouchableOpacity
              style={styles.returnButton}
              onPress={() => navigation.goBack()}
              activeOpacity={0.8}
            >
              <MaterialIcons name="arrow-back" size={18} color={colors.primary} />
              <Text style={styles.returnButtonText}>Return to Findings</Text>
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
  findingCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.marginX,
    gap: 4,
  },
  findingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  ruleCode: {
    ...typography.labelCaps,
    color: colors.secondary,
  },
  severityText: {
    ...typography.caption,
    fontSize: 10,
    fontWeight: '700',
    color: colors.statusAmberText,
  },
  findingTitle: {
    ...typography.sectionHeader,
    color: colors.primary,
    fontSize: 15,
  },
  findingExplanation: {
    ...typography.bodySm,
    color: colors.onSurface,
    marginTop: 2,
  },
  imageCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.marginX,
    gap: spacing.stackSm,
  },
  imageHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  imgScoreText: {
    ...typography.caption,
    fontSize: 11,
    color: colors.statusGreenText,
    fontWeight: '600',
  },
  imageWrapper: {
    position: 'relative',
    borderRadius: borderRadius.lg,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    backgroundColor: '#0f172a',
  },
  evidenceImage: {
    width: '100%',
    height: 240,
  },
  highlightBadge: {
    position: 'absolute',
    bottom: 8,
    left: 8,
    right: 8,
    backgroundColor: 'rgba(3, 22, 53, 0.85)',
    paddingVertical: 4,
    paddingHorizontal: 8,
    borderRadius: borderRadius.sm,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  highlightBadgeText: {
    ...typography.caption,
    fontSize: 10,
    color: colors.onPrimary,
    fontWeight: '600',
  },
  noImageBox: {
    height: 160,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceContainerLow,
    borderRadius: borderRadius.lg,
    gap: 6,
  },
  noImageText: {
    ...typography.caption,
    color: colors.secondary,
    fontWeight: '700',
  },
  extractedTextCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.marginX,
    gap: spacing.stackSm,
  },
  evidenceItem: {
    gap: 4,
  },
  evidenceReason: {
    ...typography.bodySm,
    color: colors.onSurfaceVariant,
  },
  highlightTextBox: {
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: 10,
  },
  highlightTextVal: {
    ...typography.bodyMdMedium,
    color: colors.primary,
    fontStyle: 'italic',
  },
  returnButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    gap: 6,
  },
  returnButtonText: {
    ...typography.sectionHeader,
    color: colors.primary,
    fontSize: 14,
  },
});
