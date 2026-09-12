import React, { useEffect, useRef, useCallback } from 'react';
import {
  View,
  StyleSheet,
  StatusBar,
  Platform,
  useWindowDimensions,
} from 'react-native';
import { Video, ResizeMode, AVPlaybackStatus } from 'expo-av';
import * as SplashScreen from 'expo-splash-screen';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';
import { authStorage } from '../services/authStorage';

// Static bundled intro video asset
const INTRO_VIDEO_ASSET = require('../../assets/videos/niriksha_intro.mp4');

// Fallback safety timeout in ms (video is ~5.40s; 7000ms guarantees app never hangs)
const SAFETY_TIMEOUT_MS = 7000;

export const IntroScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { width, height } = useWindowDimensions();
  const hasNavigatedRef = useRef(false);
  const targetRouteRef = useRef<'Login' | 'Dashboard'>('Login');
  const videoRef = useRef<Video | null>(null);

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

  // Single-fire idempotent navigation transition
  const navigateToDestination = useCallback((_reason: string) => {
    if (hasNavigatedRef.current) return;
    hasNavigatedRef.current = true;

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

  // Video playback status listener
  const handlePlaybackStatusUpdate = useCallback((status: AVPlaybackStatus) => {
    if (!status.isLoaded) {
      if (status.error) {
        // Fall back immediately on playback failure
        navigateToDestination('status_error');
      }
      return;
    }

    // Hide native splash when video is first ready to display
    if (status.isPlaying) {
      SplashScreen.hideAsync().catch(() => {});
    }

    // Transition immediately upon video completion
    if (status.didJustFinish) {
      navigateToDestination('video_completed');
    }
  }, [navigateToDestination]);

  const handleVideoError = useCallback((_error: string) => {
    navigateToDestination('playback_error');
  }, [navigateToDestination]);

  const handleReadyForDisplay = useCallback(() => {
    SplashScreen.hideAsync().catch(() => {});
  }, []);

  // If on desktop web with landscape orientation, frame as a mobile phone screen
  const isLandscapeWeb = Platform.OS === 'web' && width > height;

  return (
    <View style={styles.container} pointerEvents="none">
      <StatusBar hidden={true} translucent={true} barStyle="light-content" backgroundColor="#031635" />
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
        <Video
          ref={videoRef}
          source={INTRO_VIDEO_ASSET}
          style={styles.video}
          resizeMode={ResizeMode.COVER}
          shouldPlay={true}
          isLooping={false}
          useNativeControls={false}
          isMuted={Platform.OS === 'web'}
          onPlaybackStatusUpdate={handlePlaybackStatusUpdate}
          onError={handleVideoError}
          onReadyForDisplay={handleReadyForDisplay}
        />
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#031635', // Match native splash screen color to eliminate flash
    justifyContent: 'center',
    alignItems: 'center',
    width: '100%',
    height: '100%',
    overflow: 'hidden',
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
});
