import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { MaterialIcons } from '@expo/vector-icons';
import { api } from '../services/api';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const AnalyzingScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'Analyzing'>>();
  const { inspectionId, inspectionNumber } = route.params;

  const [currentStep, setCurrentStep] = useState(3); // 1 to 5
  const [progressPercent, setProgressPercent] = useState(45);

  useEffect(() => {
    let isMounted = true;

    const executeAnalysis = async () => {
      try {
        if (isMounted) {
          setCurrentStep(3);
          setProgressPercent(35);
        }
        await new Promise((r) => setTimeout(r, 600));

        if (isMounted) {
          setCurrentStep(4);
          setProgressPercent(70);
        }

        // Run OCR and Declarations extraction API
        await api.runOCR(inspectionId);

        if (isMounted) {
          setCurrentStep(5);
          setProgressPercent(100);
        }
        await new Promise((r) => setTimeout(r, 400));

        if (isMounted) {
          navigation.replace('ExtractedDeclarations', {
            inspectionId,
            inspectionNumber,
          });
        }
      } catch (err: any) {
        Alert.alert('Analysis Error', err.message || 'Failed to complete OCR extraction.', [
          {
            text: 'Go Back',
            onPress: () => navigation.goBack(),
          },
        ]);
      }
    };

    executeAnalysis();

    return () => {
      isMounted = false;
    };
  }, [inspectionId]);

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <View style={styles.card}>
          {/* Top Accent Bar */}
          <View style={styles.topAccentBar} />

          {/* Header */}
          <View style={styles.cardHeader}>
            <MaterialIcons name="query-stats" size={40} color={colors.primary} style={styles.iconCenter} />
            <Text style={styles.titleText}>Analyzing Package</Text>
            <Text style={styles.subtitleText}>Processing package images...</Text>
          </View>

          {/* Steps List */}
          <View style={styles.stepsList}>
            {/* Step 1: Done */}
            <View style={styles.stepRow}>
              <MaterialIcons name="check-circle" size={20} color={colors.statusGreenText} />
              <Text style={styles.stepTextDone}>Images uploaded</Text>
            </View>

            {/* Step 2: Done */}
            <View style={styles.stepRow}>
              <MaterialIcons name="check-circle" size={20} color={colors.statusGreenText} />
              <Text style={styles.stepTextDone}>Image quality checked</Text>
            </View>

            {/* Step 3: Done */}
            <View style={styles.stepRow}>
              <MaterialIcons
                name={currentStep >= 3 ? 'check-circle' : 'radio-button-unchecked'}
                size={20}
                color={currentStep >= 3 ? colors.statusGreenText : colors.secondary}
              />
              <Text style={currentStep >= 3 ? styles.stepTextDone : styles.stepTextPending}>
                Reading package text
              </Text>
            </View>

            {/* Step 4: Active */}
            <View style={styles.stepRowActive}>
              <MaterialIcons
                name={currentStep > 4 ? 'check-circle' : 'sync'}
                size={20}
                color={currentStep > 4 ? colors.statusGreenText : colors.primary}
              />
              <View style={styles.activeStepContent}>
                <View style={styles.activeLabelRow}>
                  <Text style={styles.stepTextActive}>Extracting declarations</Text>
                  <Text style={styles.progressPercentText}>{progressPercent}%</Text>
                </View>
                <View style={styles.progressBarBg}>
                  <View style={[styles.progressBarFill, { width: `${progressPercent}%` }]} />
                </View>
              </View>
            </View>

            {/* Step 5: Pending */}
            <View style={[styles.stepRow, currentStep < 5 && styles.stepRowDim]}>
              <MaterialIcons
                name={currentStep >= 5 ? 'check-circle' : 'radio-button-unchecked'}
                size={20}
                color={currentStep >= 5 ? colors.statusGreenText : colors.secondary}
              />
              <Text style={currentStep >= 5 ? styles.stepTextDone : styles.stepTextPending}>
                Checking compliance rules
              </Text>
            </View>
          </View>

          {/* Cancel Button */}
          <View style={styles.cancelSection}>
            <TouchableOpacity
              style={styles.cancelButton}
              onPress={() => navigation.goBack()}
              activeOpacity={0.8}
            >
              <Text style={styles.cancelButtonText}>CANCEL ANALYSIS</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.surface,
  },
  container: {
    flex: 1,
    backgroundColor: colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.gutter,
  },
  card: {
    width: '100%',
    maxWidth: 420,
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    padding: 24,
    position: 'relative',
    overflow: 'hidden',
  },
  topAccentBar: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    height: 4,
    backgroundColor: colors.primary,
  },
  cardHeader: {
    alignItems: 'center',
    marginBottom: 24,
    marginTop: 4,
  },
  iconCenter: {
    marginBottom: 8,
  },
  titleText: {
    ...typography.headlineLg,
    fontSize: 20,
    lineHeight: 28,
    fontWeight: '700',
    color: colors.primary,
    marginBottom: 4,
    textAlign: 'center',
  },
  subtitleText: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.secondary,
    textAlign: 'center',
  },
  stepsList: {
    gap: 16,
  },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  stepRowDim: {
    opacity: 0.5,
  },
  stepRowActive: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
  },
  stepTextDone: {
    ...typography.bodyMd,
    fontSize: 14,
    lineHeight: 20,
    color: colors.onSurface,
  },
  stepTextPending: {
    ...typography.bodyMd,
    fontSize: 14,
    lineHeight: 20,
    color: colors.secondary,
  },
  activeStepContent: {
    flex: 1,
    gap: 4,
  },
  activeLabelRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  stepTextActive: {
    ...typography.bodyMd,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '600',
    color: colors.primary,
  },
  progressPercentText: {
    ...typography.caption,
    fontSize: 12,
    color: colors.secondary,
  },
  progressBarBg: {
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.surfaceVariant,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    overflow: 'hidden',
  },
  progressBarFill: {
    height: '100%',
    backgroundColor: colors.primary,
    borderRadius: 3,
  },
  cancelSection: {
    marginTop: 28,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: colors.borderSubtle,
    alignItems: 'center',
  },
  cancelButton: {
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    borderColor: colors.primary,
  },
  cancelButtonText: {
    ...typography.labelCaps,
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 0.5,
    fontWeight: '600',
    color: colors.primary,
  },
});

