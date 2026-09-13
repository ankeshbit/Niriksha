import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  View,
  Text,
  Image,
  TouchableOpacity,
  ActivityIndicator,
  StyleSheet,
  StatusBar,
  Platform,
  useWindowDimensions,
} from 'react-native';
import { Video, ResizeMode, AVPlaybackStatus } from 'expo-av';
import { Asset } from 'expo-asset';
import * as SplashScreen from 'expo-splash-screen';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';
import { authStorage } from '../services/authStorage';

// Bundled static assets
export const INTRO_VIDEO_ASSET = require('../../assets/videos/niriksha_intro.mp4');
export const NIRIKSHA_LOGO_ASSET = require('../../assets/niriksha_logo.png');

// Android compiled raw resource URI (100% offline inside APK, zero network required)
export const ANDROID_RAW_RESOURCE_URI = 'android.resource://gov.doca.legalmetrology/raw/niriksha_intro';

// Fallback safety timeout in ms (video is ~5.41s; 8000ms guarantees app never hangs)
const SAFETY_TIMEOUT_MS = 8000;

export const IntroScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { width, height } = useWindowDimensions();
  const hasNavigatedRef = useRef(false);
  const targetRouteRef = useRef<'Login' | 'Dashboard'>('Login');
  const videoRef = useRef<Video | null>(null);

  // Preferred source: native raw resource on Android, bundled required asset on Web/iOS
  const [videoSource, setVideoSource] = useState<any>(
    Platform.OS === 'android' ? { uri: ANDROID_RAW_RESOURCE_URI } : INTRO_VIDEO_ASSET
  );
  const [isVideoLoaded, setIsVideoLoaded] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const hasAttemptedFallbackRef = useRef(false);

  // Pre-resolve authentication state while video is playing
  useEffect(() => {
    let isMounted = true;

    Promise.all([authStorage.getToken(), authStorage.getProfile()])
      .then(([token, profile]) => {
        if (!isMounted) return;
        if (token) {
          if (profile?.role && profile.role !== 'INSPECTOR') {
            authStorage.clear().catch(() => {});
            targetRouteRef.current = 'Login';
          } else {
            targetRouteRef.current = 'Dashboard';
          }
        } else {
          targetRouteRef.current = 'Login';
        }
      })
      .catch(() => {
        if (!isMounted) return;
        targetRouteRef.current = 'Login';
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // Preload asset in background so local file cache is ready if raw resource is unavailable
  useEffect(() => {
    // Hide native splash screen after 350ms so Android never stays stuck on native splash
    const splashTimer = setTimeout(() => {
      SplashScreen.hideAsync().catch(() => {});
    }, 350);

    Asset.loadAsync(INTRO_VIDEO_ASSET).catch((err) => {
      console.warn('[IntroScreen] Asset pre-cache notice:', err);
    });

    return () => {
      clearTimeout(splashTimer);
    };
  }, []);

  // Single-fire idempotent navigation transition
  const navigateToDestination = useCallback((reason: string) => {
    if (hasNavigatedRef.current) return;
    hasNavigatedRef.current = true;

    console.log(`[IntroScreen] Navigating to destination (${targetRouteRef.current}) via reason: ${reason}`);

    // Unload video player if active
    if (videoRef.current) {
      videoRef.current.unloadAsync().catch(() => {});
    }

    // Hide native splash screen if not already hidden
    SplashScreen.hideAsync().catch(() => {});

    // Reset navigation stack to target destination (removes Intro from back history)
    const destination = targetRouteRef.current;
    navigation.reset({
      index: 0,
      routes: [{ name: destination }],
    });
  }, [navigation]);

  // Fallback safety timeout
  useEffect(() => {
    const timer = setTimeout(() => {
      navigateToDestination('safety_timeout');
    }, SAFETY_TIMEOUT_MS);

    return () => {
      clearTimeout(timer);
    };
  }, [navigateToDestination]);

  // Error recovery logic
  const handlePlaybackFailure = useCallback((errorDetails: any) => {
    console.error('[IntroScreen] Video playback issue detected:', errorDetails);

    // If running on Android with raw resource URI and it fails (e.g. in Expo Go where APK raw is not compiled),
    // immediately retry with the JS bundled asset module
    if (Platform.OS === 'android' && !hasAttemptedFallbackRef.current) {
      hasAttemptedFallbackRef.current = true;
      console.log('[IntroScreen] Retrying with bundled asset module...');
      setVideoSource(INTRO_VIDEO_ASSET);
      return;
    }

    // If both attempts fail, show the controlled fallback screen with Logo + Loading + Continue
    setHasError(true);
    setErrorMessage(typeof errorDetails === 'string' ? errorDetails : 'Unable to play intro video.');
    SplashScreen.hideAsync().catch(() => {});

    // Controlled auto-advance so the user is never stuck
    setTimeout(() => {
      navigateToDestination('fallback_auto_advance');
    }, 3000);
  }, [navigateToDestination]);

  // Video playback status listener
  const handlePlaybackStatusUpdate = useCallback((status: AVPlaybackStatus) => {
    if (!status.isLoaded) {
      if (status.error) {
        handlePlaybackFailure(status.error);
      }
      return;
    }

    setIsVideoLoaded(true);

    // Hide native splash when video is loaded and ready
    SplashScreen.hideAsync().catch(() => {});

    // Transition immediately upon video completion
    if (status.didJustFinish) {
      navigateToDestination('video_completed');
    }
  }, [handlePlaybackFailure, navigateToDestination]);

  const handleVideoError = useCallback((error: string) => {
    handlePlaybackFailure(error);
  }, [handlePlaybackFailure]);

  const handleReadyForDisplay = useCallback(() => {
    setIsVideoLoaded(true);
    SplashScreen.hideAsync().catch(() => {});
  }, []);

  // If on desktop web with landscape orientation, frame as a mobile phone screen
  const isLandscapeWeb = Platform.OS === 'web' && width > height;

  return (
    <View style={styles.container}>
      <StatusBar hidden={true} translucent={true} barStyle="light-content" backgroundColor="#031635" />

      {/* Skip Button: Allows immediate bypass */}
      <TouchableOpacity
        style={styles.skipButton}
        onPress={() => navigateToDestination('user_skipped')}
        activeOpacity={0.7}
        accessibilityLabel="Skip intro video"
      >
        <Text style={styles.skipButtonText}>SKIP ›</Text>
      </TouchableOpacity>

      {/* Fallback View: Shown if video fails or while waiting */}
      {hasError ? (
        <View style={styles.fallbackContainer}>
          <Image source={NIRIKSHA_LOGO_ASSET} style={styles.fallbackLogo} />
          <Text style={styles.fallbackTitle}>NiriKsha</Text>
          <Text style={styles.fallbackSubtitle}>Department of Consumer Affairs • Legal Metrology</Text>

          <View style={styles.loadingRow}>
            <ActivityIndicator size="small" color="#ffffff" />
            <Text style={styles.loadingText}>Loading application...</Text>
          </View>

          <TouchableOpacity
            style={styles.continueBtn}
            onPress={() => navigateToDestination('user_continue_pressed')}
            activeOpacity={0.8}
          >
            <Text style={styles.continueBtnText}>Continue to Login →</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <View
          style={[
            styles.videoWrapper,
            isLandscapeWeb && {
              width: Math.min(480, height * (9 / 16)),
              height: '100%',
              maxHeight: height,
              borderRadius: 20,
              overflow: 'hidden',
            },
          ]}
        >
          {/* Subtle loading placeholder until first frame arrives */}
          {!isVideoLoaded && (
            <View style={styles.preVideoPlaceholder}>
              <Image source={NIRIKSHA_LOGO_ASSET} style={styles.placeholderLogo} />
              <ActivityIndicator size="small" color="#ffffff" style={{ marginTop: 16 }} />
            </View>
          )}

          <Video
            ref={videoRef}
            source={videoSource}
            style={[styles.video, !isVideoLoaded && { opacity: 0 }]}
            resizeMode={ResizeMode.CONTAIN}
            shouldPlay={true}
            isLooping={false}
            useNativeControls={false}
            isMuted={Platform.OS === 'web'}
            onPlaybackStatusUpdate={handlePlaybackStatusUpdate}
            onError={handleVideoError}
            onReadyForDisplay={handleReadyForDisplay}
          />
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#031635', // Match native splash and video background color
    justifyContent: 'center',
    alignItems: 'center',
    width: '100%',
    height: '100%',
    overflow: 'hidden',
  },
  skipButton: {
    position: 'absolute',
    top: Platform.OS === 'ios' ? 52 : 36,
    right: 18,
    backgroundColor: 'rgba(255, 255, 255, 0.18)',
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.25)',
    zIndex: 50,
  },
  skipButtonText: {
    color: '#ffffff',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1,
  },
  videoWrapper: {
    flex: 1,
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
    backgroundColor: '#031635',
  },
  video: {
    position: 'absolute',
    top: 0,
    left: 0,
    bottom: 0,
    right: 0,
    width: '100%',
    height: '100%',
    backgroundColor: '#031635',
  },
  preVideoPlaceholder: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#031635',
    zIndex: 1,
  },
  placeholderLogo: {
    width: 90,
    height: 90,
    resizeMode: 'contain',
    opacity: 0.85,
  },
  fallbackContainer: {
    flex: 1,
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 24,
    backgroundColor: '#031635',
  },
  fallbackLogo: {
    width: 100,
    height: 100,
    resizeMode: 'contain',
    marginBottom: 16,
  },
  fallbackTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: '#ffffff',
    letterSpacing: 1,
    marginBottom: 4,
  },
  fallbackSubtitle: {
    fontSize: 12,
    color: 'rgba(255, 255, 255, 0.7)',
    textAlign: 'center',
    marginBottom: 24,
  },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 24,
  },
  loadingText: {
    fontSize: 13,
    color: 'rgba(255, 255, 255, 0.85)',
  },
  continueBtn: {
    backgroundColor: '#2563eb',
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 8,
    marginTop: 4,
  },
  continueBtnText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '600',
  },
});
