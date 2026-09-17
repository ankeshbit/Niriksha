import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Animated,
  Easing,
  Platform,
  AccessibilityInfo,
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

export interface SpinningIconProps {
  size?: number;
  color?: string;
  active?: boolean;
  accessibilityLabel?: string;
  testID?: string;
}

export const SpinningIcon: React.FC<SpinningIconProps> = ({
  size = 20,
  color,
  active = true,
  accessibilityLabel = 'Processing',
  testID = 'spinning-icon',
}) => {
  const isWeb = Platform.OS === 'web';
  const spinAnim = useRef(new Animated.Value(0)).current;
  const animLoopRef = useRef<Animated.CompositeAnimation | null>(null);
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    let isMounted = true;

    // Respect accessibility settings for reduced motion
    AccessibilityInfo.isReduceMotionEnabled()
      .then((enabled) => {
        if (isMounted) setReduceMotion(Boolean(enabled));
      })
      .catch(() => {});

    let subscription: any = null;
    try {
      subscription = AccessibilityInfo.addEventListener(
        'reduceMotionChanged',
        (enabled: boolean) => {
          if (isMounted) setReduceMotion(Boolean(enabled));
        }
      );
    } catch {
      // Platform / version fallback
    }

    return () => {
      isMounted = false;
      if (subscription && typeof subscription.remove === 'function') {
        subscription.remove();
      }
    };
  }, []);

  useEffect(() => {
    // Stop any existing animation loop immediately
    if (animLoopRef.current) {
      animLoopRef.current.stop();
      animLoopRef.current = null;
    }
    spinAnim.stopAnimation();

    if (!active || reduceMotion) {
      spinAnim.setValue(0);
      return;
    }

    spinAnim.setValue(0);
    const loop = Animated.loop(
      Animated.timing(spinAnim, {
        toValue: 1,
        duration: 900,
        easing: Easing.linear,
        useNativeDriver: !isWeb,
      }),
      { iterations: -1, resetBeforeIteration: true }
    );
    animLoopRef.current = loop;
    loop.start();

    return () => {
      if (animLoopRef.current) {
        animLoopRef.current.stop();
        animLoopRef.current = null;
      }
      spinAnim.stopAnimation();
    };
  }, [active, reduceMotion, isWeb]);

  const rotate = spinAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });

  return (
    <Animated.View
      collapsable={false}
      testID={testID}
      accessibilityRole="progressbar"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ busy: active }}
      style={{
        width: size,
        height: size,
        justifyContent: 'center',
        alignItems: 'center',
        transform: [{ rotate }],
      }}
    >
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
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [errorTitle, setErrorTitle] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  // Abort controller ref — lets us cancel in-flight OCR request on unmount/cancel
  const abortRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef(true);
  const hasExecutedRef = useRef(false);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  // Live timer for active analysis stages
  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null;
    if (['STARTING', 'OCR', 'EXTRACTION', 'COMPLIANCE'].includes(stage)) {
      interval = setInterval(() => {
        setElapsedSeconds((s) => s + 1);
      }, 1000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [stage]);

  useEffect(() => {
    if (hasExecutedRef.current) return;
    hasExecutedRef.current = true;

    const executeAnalysis = async () => {
      if (!isMountedRef.current) return;

      // Stage 1: STARTING — Check existing inspection state & prepare pipeline
      setStage('STARTING');
      setProgressPercent(20);
      abortRef.current = new AbortController();
      console.log('[ANALYZING_SCREEN] Starting analysis pipeline', { inspectionId, stage: 'STARTING' });

      // Pre-check if OCR is already complete or in-flight on server
      let alreadyExtracted = false;
      let inProgressOnBackend = false;
      try {
        const initialCheck = await api.getInspection(inspectionId);
        const st = initialCheck?.status;
        if (
          st === 'EXTRACTION_COMPLETE' ||
          st === 'COMPLETED' ||
          st === 'UNDER_REVIEW' ||
          st === 'EVALUATION_COMPLETE'
        ) {
          alreadyExtracted = true;
          console.log('[ANALYZING_SCREEN] OCR already completed on backend. Reusing results.', { inspectionId, status: st });
        } else if (st === 'OCR_PROCESSING') {
          inProgressOnBackend = true;
          console.log('[ANALYZING_SCREEN] OCR already in progress on backend. Will await server completion.', { inspectionId });
        }
      } catch (initialErr) {
        console.warn('[ANALYZING_SCREEN] Status pre-check warning:', initialErr);
      }

      if (!isMountedRef.current || abortRef.current?.signal.aborted) return;

      // Stage 2: OCR — run PaddleOCR or wait for in-progress OCR
      setStage('OCR');
      setProgressPercent(40);

      const ocrStart = Date.now();
      let ocrRes: any = null;

      if (alreadyExtracted) {
        console.log('[ANALYZING_SCREEN] Step 3 OCR fast-path hit. Reusing extracted declarations.');
      } else if (inProgressOnBackend) {
        console.log('[ANALYZING_SCREEN] Step 3: Awaiting in-flight server OCR completion...');
        let finished = false;
        const pollStart = Date.now();
        // Poll for up to 600s (10 minutes)
        while (!finished && Date.now() - pollStart < 600000) {
          if (!isMountedRef.current || abortRef.current?.signal.aborted) return;
          await new Promise<void>((r) => setTimeout(r, 3000));
          try {
            const inspStatus = await api.getInspection(inspectionId);
            const curSt = inspStatus?.status;
            if (
              curSt === 'EXTRACTION_COMPLETE' ||
              curSt === 'COMPLETED' ||
              curSt === 'UNDER_REVIEW' ||
              curSt === 'EVALUATION_COMPLETE'
            ) {
              finished = true;
              break;
            } else if (curSt === 'OCR_FAILED') {
              throw new Error('OCR text recognition failed on server.');
            }
          } catch (pollErr: any) {
            if (pollErr?.message?.includes('failed on server')) throw pollErr;
          }
        }
        if (!finished) {
          throw new Error('OCR processing timed out on server.');
        }
      } else {
        console.log('[ANALYZING_SCREEN] Step 3: Running OCR and text recognition', { inspectionId, stage: 'OCR' });
        try {
          ocrRes = await api.runOCR(inspectionId, { signal: abortRef.current?.signal });
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

          // Check if backend is still actively processing before showing error
          let backendStillProcessing = false;
          try {
            const statusCheck = await api.getInspection(inspectionId);
            const bStatus = statusCheck?.status;
            if (
              bStatus === 'EXTRACTION_COMPLETE' ||
              bStatus === 'COMPLETED' ||
              bStatus === 'UNDER_REVIEW' ||
              bStatus === 'EVALUATION_COMPLETE'
            ) {
              alreadyExtracted = true;
              console.log('[ANALYZING_SCREEN] Backend completed at timeout boundary. Proceeding.');
            } else if (bStatus === 'OCR_PROCESSING') {
              backendStillProcessing = true;
            }
          } catch {
            // Cannot reach backend to check status
          }

          if (backendStillProcessing) {
            console.log('[ANALYZING_SCREEN] Backend is still actively processing OCR. Switching to polling mode.');
            let pollFinished = false;
            const pollStart = Date.now();
            while (!pollFinished && Date.now() - pollStart < 600000) {
              if (!isMountedRef.current) return;
              await new Promise<void>((r) => setTimeout(r, 3000));
              try {
                const s = await api.getInspection(inspectionId);
                const curSt = s?.status;
                if (
                  curSt === 'EXTRACTION_COMPLETE' ||
                  curSt === 'COMPLETED' ||
                  curSt === 'UNDER_REVIEW' ||
                  curSt === 'EVALUATION_COMPLETE'
                ) {
                  pollFinished = true;
                  break;
                } else if (curSt === 'OCR_FAILED') {
                  throw new Error('OCR text recognition failed on server.');
                }
              } catch (pe: any) {
                if (pe?.message?.includes('failed on server')) throw pe;
              }
            }
            if (!pollFinished) {
              setStage('ERROR');
              setErrorTitle('Analysis Taking Longer Than Expected');
              setErrorMessage(
                'OCR processing is taking longer than expected. ' +
                'Your inspection and images are safely saved — please go back and retry.'
              );
              return;
            }
          } else if (!alreadyExtracted) {
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
            } else if (classified.type === 'SERVER_ERROR') {
              title = 'Server Error During Analysis';
              message = classified.userMessage || 'The server encountered an error while processing package images.';
            } else if (classified.type === 'AUTH_ERROR') {
              title = 'Session Expired';
              message = classified.userMessage || 'Your session has expired. Please sign in again.';
            }

            setStage('ERROR');
            setErrorTitle(title);
            setErrorMessage(message);
            return;
          }
        }
      }

      if (!isMountedRef.current) return;

      // Stage 3: EXTRACTION — statutory declaration consolidation
      setStage('EXTRACTION');
      setProgressPercent(70);
      console.log('[ANALYZING_SCREEN] Step 4: Extracting statutory declarations', { inspectionId, stage: 'EXTRACTION' });

      try {
        const declsRes = await api.getDeclarations(inspectionId);
        console.log('[ANALYZING_SCREEN] Step 4 Declarations confirmed on backend', {
          inspectionId,
          count: Array.isArray(declsRes) ? declsRes.length : 0,
        });
      } catch (declErr: any) {
        if (!isMountedRef.current) return;
        const classified = classifyFetchError(declErr);
        console.error('[ANALYZING_SCREEN_ERROR] Declarations retrieval failed', {
          inspectionId,
          stage: 'EXTRACTION',
          errorType: classified.type,
          message: classified.message,
        });
        setStage('ERROR');
        setErrorTitle('Declaration Extraction Failed');
        setErrorMessage(
          classified.userMessage ||
          'Failed to retrieve extracted package declarations. Please go back and retry.'
        );
        return;
      }

      if (!isMountedRef.current) return;

      // Stage 4: COMPLIANCE — evaluate deterministic legal metrology rules
      setStage('COMPLIANCE');
      setProgressPercent(90);
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
        console.warn('[ANALYZING_SCREEN] Continuing to declarations screen despite eval error');
      }

      if (!isMountedRef.current) return;

      // Stage 5: COMPLETED — all steps finished
      setStage('COMPLETED');
      setProgressPercent(100);
      console.log('[ANALYZING_SCREEN] Analysis complete (100%), navigating to ExtractedDeclarations', { inspectionId });

      await new Promise<void>((r) => setTimeout(r, 500));
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
                ? `Running AI text recognition (${elapsedSeconds}s)...`
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
                    <SpinningIcon
                      size={20}
                      color={colors.primary}
                      active={step3Active}
                      accessibilityLabel="Reading package text in progress"
                      testID="step-ocr-spinner"
                    />
                  ) : (
                    <MaterialIcons name="radio-button-unchecked" size={20} color={colors.secondary} />
                  )}
                  <Text style={step3Done ? styles.stepTextDone : (step3Active ? styles.stepTextActive : styles.stepTextPending)}>
                    Reading package text {step3Active ? `(${elapsedSeconds}s)` : ''}
                  </Text>
                </View>

                {/* Step 4: Extracting declarations */}
                <View style={step4Active ? styles.stepRowActive : styles.stepRow}>
                  {step4Done ? (
                    <MaterialIcons name="check-circle" size={20} color={colors.statusGreenText} />
                  ) : step4Active ? (
                    <SpinningIcon
                      size={20}
                      color={colors.primary}
                      active={step4Active}
                      accessibilityLabel="Extracting declarations in progress"
                      testID="step-extraction-spinner"
                    />
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
                    <SpinningIcon
                      size={20}
                      color={colors.primary}
                      active={step5Active}
                      accessibilityLabel="Checking compliance rules in progress"
                      testID="step-compliance-spinner"
                    />
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
