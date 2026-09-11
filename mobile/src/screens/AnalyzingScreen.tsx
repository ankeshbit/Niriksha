import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Animated,
  Easing,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { MaterialIcons } from '@expo/vector-icons';
import { api, classifyFetchError } from '../services/api';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

// ─── Analysis stage enum ───────────────────────────────────────────────────────

type AnalysisStage =
  | 'IDLE'
  | 'STARTING'
  | 'OCR'
  | 'EXTRACTION'
  | 'COMPLIANCE'
  | 'COMPLETED'
  | 'ERROR'
  | 'CANCELLED';

// ─── SpinningIcon — animated rotating sync icon ────────────────────────────────

const SpinningIcon: React.FC<{ size?: number; color?: string }> = ({
  size = 20,
  color,
}) => {
  const isWeb = Platform.OS === 'web';
  const spinAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.timing(spinAnim, {
        toValue: 1,
        duration: 900,
        easing: Easing.linear,
        useNativeDriver: !isWeb,
      })
    );
    loop.start();
    return () => loop.stop();
  }, []);

  const rotate = spinAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });

  return (
    <Animated.View style={{ transform: [{ rotate }] }}>
      <MaterialIcons name="sync" size={size} color={color || colors.primary} />
    </Animated.View>
  );
};

// ─── Animated progress bar ────────────────────────────────────────────────────

const AnimatedProgressBar: React.FC<{ percent: number }> = ({ percent }) => {
  const widthAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(widthAnim, {
      toValue: percent,
      duration: 400,
      easing: Easing.out(Easing.ease),
      useNativeDriver: false,
    }).start();
  }, [percent]);

  const widthInterpolated = widthAnim.interpolate({
    inputRange: [0, 100],
    outputRange: ['0%', '100%'],
    extrapolate: 'clamp',
  });

  return (
    <View style={styles.progressBarBg}>
      <Animated.View style={[styles.progressBarFill, { width: widthInterpolated }]} />
    </View>
  );
};

// ─── AnalyzingScreen ──────────────────────────────────────────────────────────

export const AnalyzingScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'Analyzing'>>();
  const { inspectionId, inspectionNumber } = route.params;

  const [stage, setStage] = useState<AnalysisStage>('IDLE');
  const [progressPercent, setProgressPercent] = useState(15);
  const [errorTitle, setErrorTitle] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  // Abort controller ref — lets us cancel in-flight OCR request on unmount/cancel
  const abortRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    const executeAnalysis = async () => {
      if (!isMountedRef.current) return;

      // Stage 1: STARTING — images were already uploaded before this screen
      setStage('STARTING');
      setProgressPercent(20);
      console.log('[ANALYZING_SCREEN] Starting analysis pipeline', { inspectionId, stage: 'STARTING' });

      await new Promise<void>((r) => setTimeout(r, 400));
      if (!isMountedRef.current) return;

      // Stage 2: OCR — run PaddleOCR on server
      setStage('OCR');
      setProgressPercent(40);
      console.log('[ANALYZING_SCREEN] Step 3: Running OCR and text recognition', { inspectionId, stage: 'OCR' });

      const ocrStart = Date.now();
      let ocrRes: any = null;

      try {
        ocrRes = await api.runOCR(inspectionId);
        const ocrDuration = Date.now() - ocrStart;
        console.log('[ANALYZING_SCREEN] Step 3 OCR complete', {
          inspectionId,
          durationMs: ocrDuration,
          declarationsCount: ocrRes?.declarations_count,
        });
      } catch (err: any) {
        if (!isMountedRef.current) return;
        const ocrDuration = Date.now() - ocrStart;
        const classified = classifyFetchError(err);

        console.error('[ANALYZING_SCREEN_ERROR] OCR failed', {
          inspectionId,
          stage: 'OCR',
          durationMs: ocrDuration,
          errorType: classified.type,
          message: classified.message,
        });

        let title = 'Analysis Error';
        let message = classified.userMessage || err.message || 'Failed to complete OCR extraction.';

        if (classified.type === 'REQUEST_TIMEOUT') {
          title = 'Analysis Taking Longer Than Expected';
          message =
            'OCR processing is taking longer than expected. ' +
            'Your inspection and images are safely saved — please go back and retry.';
        } else if (classified.type === 'NETWORK_UNREACHABLE') {
          title = 'Connection Lost During Analysis';
          message =
            'Connection to the server was lost during OCR. ' +
            'Your inspection and images are safely saved. Please retry when connected.';
        }

        setStage('ERROR');
        setErrorTitle(title);
        setErrorMessage(message);
        return;
      }

      if (!isMountedRef.current) return;

      // Stage 3: EXTRACTION — statutory declaration consolidation
      setStage('EXTRACTION');
      setProgressPercent(65);
      console.log('[ANALYZING_SCREEN] Step 4: Extracting statutory declarations', { inspectionId, stage: 'EXTRACTION' });

      await new Promise<void>((r) => setTimeout(r, 500));
      if (!isMountedRef.current) return;

      // Stage 4: COMPLIANCE — evaluate deterministic legal metrology rules
      setStage('COMPLIANCE');
      setProgressPercent(85);
      console.log('[ANALYZING_SCREEN] Step 5: Evaluating compliance rules', { inspectionId, stage: 'COMPLIANCE' });

      const evalStart = Date.now();
      try {
        const evalRes = await api.evaluateRules(inspectionId);
        const evalDuration = Date.now() - evalStart;
        console.log('[ANALYZING_SCREEN] Step 5 Compliance rules evaluated', {
          inspectionId,
          durationMs: evalDuration,
          findingsCount: evalRes?.findings_count,
          overallStatus: evalRes?.overall_status,
        });
      } catch (err: any) {
        if (!isMountedRef.current) return;
        const classified = classifyFetchError(err);
        console.error('[ANALYZING_SCREEN_ERROR] Rule evaluation error', {
          inspectionId,
          stage: 'COMPLIANCE',
          errorType: classified.type,
          message: classified.message,
        });
        // Non-fatal: if rules evaluation fails here, inspector can still evaluate on ExtractedDeclarations screen
        console.warn('[ANALYZING_SCREEN] Continuing to declarations screen despite eval error');
      }

      if (!isMountedRef.current) return;

      // Stage 5: COMPLETED — all 5 steps finished
      setStage('COMPLETED');
      setProgressPercent(100);
      console.log('[ANALYZING_SCREEN] Analysis complete (100%), navigating to ExtractedDeclarations', { inspectionId });

      await new Promise<void>((r) => setTimeout(r, 600));
      if (!isMountedRef.current) return;

      navigation.replace('ExtractedDeclarations', {
        inspectionId,
        inspectionNumber,
      });
    };

    executeAnalysis();
  }, [inspectionId]);

  // Step state derivation
  const step3Active = stage === 'OCR';
  const step3Done = ['EXTRACTION', 'COMPLIANCE', 'COMPLETED'].includes(stage);

  const step4Active = stage === 'EXTRACTION';
  const step4Done = ['COMPLIANCE', 'COMPLETED'].includes(stage);

  const step5Active = stage === 'COMPLIANCE';
  const step5Done = stage === 'COMPLETED';

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <View style={styles.card}>
          {/* Top Accent Bar */}
          <View style={styles.topAccentBar} />

          {/* Header */}
          <View style={styles.cardHeader}>
            <MaterialIcons name="query-stats" size={40} color={colors.primary} style={styles.iconCenter} />
            <Text style={styles.titleText}>
              {stage === 'ERROR' ? 'Analysis Error' : 'Analyzing Package'}
            </Text>
            <Text style={styles.subtitleText}>
              {stage === 'IDLE' || stage === 'STARTING'
                ? 'Preparing package data...'
                : stage === 'OCR'
                ? 'Running AI text recognition...'
                : stage === 'EXTRACTION'
                ? 'Parsing statutory declarations...'
                : stage === 'COMPLIANCE'
                ? 'Checking Legal Metrology compliance rules...'
                : stage === 'COMPLETED'
                ? 'Analysis complete!'
                : stage === 'ERROR'
                ? errorTitle
                : 'Processing...'}
            </Text>
          </View>

          {stage === 'ERROR' ? (
            <View style={styles.errorContainer}>
              <MaterialIcons name="error-outline" size={32} color={colors.error || '#DC2626'} />
              <Text style={styles.errorText}>{errorMessage}</Text>
              <TouchableOpacity
                style={styles.retryButton}
                onPress={() => navigation.goBack()}
              >
                <Text style={styles.retryButtonText}>GO BACK & RETRY</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <>
              {/* Overall Progress Bar */}
              <View style={styles.progressContainer}>
                <View style={styles.progressHeaderRow}>
                  <Text style={styles.progressLabel}>Overall Progress</Text>
                  <Text style={styles.progressPercentText}>{progressPercent}%</Text>
                </View>
                <AnimatedProgressBar percent={progressPercent} />
              </View>

              {/* Steps List */}
              <View style={styles.stepsList}>
                {/* Step 1: Images uploaded — always done (pre-condition) */}
                <View style={styles.stepRow}>
                  <MaterialIcons name="check-circle" size={20} color={colors.statusGreenText} />
                  <Text style={styles.stepTextDone}>Images uploaded</Text>
                </View>

                {/* Step 2: Image quality checked — always done */}
                <View style={styles.stepRow}>
                  <MaterialIcons name="check-circle" size={20} color={colors.statusGreenText} />
                  <Text style={styles.stepTextDone}>Image quality checked</Text>
                </View>

                {/* Step 3: Reading package text (OCR) */}
                <View style={step3Active ? styles.stepRowActive : styles.stepRow}>
                  {step3Done ? (
                    <MaterialIcons name="check-circle" size={20} color={colors.statusGreenText} />
                  ) : step3Active ? (
                    <SpinningIcon size={20} color={colors.primary} />
                  ) : (
                    <MaterialIcons name="radio-button-unchecked" size={20} color={colors.secondary} />
                  )}
                  <Text style={step3Done ? styles.stepTextDone : (step3Active ? styles.stepTextActive : styles.stepTextPending)}>
                    Reading package text
                  </Text>
                </View>

                {/* Step 4: Extracting declarations */}
                <View style={step4Active ? styles.stepRowActive : styles.stepRow}>
                  {step4Done ? (
                    <MaterialIcons name="check-circle" size={20} color={colors.statusGreenText} />
                  ) : step4Active ? (
                    <SpinningIcon size={20} color={colors.primary} />
                  ) : (
                    <MaterialIcons name="radio-button-unchecked" size={20} color={colors.secondary} />
                  )}
                  <Text style={step4Done ? styles.stepTextDone : (step4Active ? styles.stepTextActive : styles.stepTextPending)}>
                    Extracting declarations
                  </Text>
                </View>

                {/* Step 5: Checking compliance rules */}
                <View style={step5Active ? styles.stepRowActive : [styles.stepRow, !step5Done && styles.stepRowDim]}>
                  {step5Done ? (
                    <MaterialIcons name="check-circle" size={20} color={colors.statusGreenText} />
                  ) : step5Active ? (
                    <SpinningIcon size={20} color={colors.primary} />
                  ) : (
                    <MaterialIcons name="radio-button-unchecked" size={20} color={colors.secondary} />
                  )}
                  <Text style={step5Done ? styles.stepTextDone : (step5Active ? styles.stepTextActive : styles.stepTextPending)}>
                    Checking compliance rules
                  </Text>
                </View>
              </View>

              {/* Cancel Button */}
              <View style={styles.cancelSection}>
                <TouchableOpacity
                  style={styles.cancelButton}
                  onPress={() => {
                    abortRef.current?.abort();
                    navigation.goBack();
                  }}
                  activeOpacity={0.8}
                >
                  <Text style={styles.cancelButtonText}>CANCEL ANALYSIS</Text>
                </TouchableOpacity>
              </View>
            </>
          )}
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
  progressContainer: {
    marginBottom: 20,
    gap: 6,
  },
  progressHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  progressLabel: {
    ...typography.bodySm,
    fontSize: 12,
    fontWeight: '600',
    color: colors.secondary,
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
  errorContainer: {
    alignItems: 'center',
    gap: 12,
    paddingVertical: 8,
  },
  errorText: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 19,
    color: colors.onSurface,
    textAlign: 'center',
  },
  retryButton: {
    marginTop: 8,
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: borderRadius.DEFAULT,
    backgroundColor: colors.primary,
  },
  retryButtonText: {
    ...typography.labelCaps,
    fontSize: 12,
    letterSpacing: 0.5,
    fontWeight: '700',
    color: colors.onPrimary,
  },
});
