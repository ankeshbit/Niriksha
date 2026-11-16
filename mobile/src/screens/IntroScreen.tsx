import React, { useEffect } from 'react';
import {
  View,
  Text,
  Image,
  ActivityIndicator,
  StyleSheet,
  StatusBar,
} from 'react-native';
import * as SplashScreen from 'expo-splash-screen';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';
import { authStorage } from '../services/authStorage';

export const NIRIKSHA_LOGO_ASSET = require('../../assets/niriksha_logo.png');

export const IntroScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();

  useEffect(() => {
    let isMounted = true;
    SplashScreen.hideAsync().catch(() => {});

    Promise.all([authStorage.getToken(), authStorage.getProfile()])
      .then(([token, profile]) => {
        if (!isMounted) return;
        if (token) {
          if (profile?.role === 'SUPERVISOR') {
            navigation.reset({
              index: 0,
              routes: [{ name: 'SupervisorDashboard' }],
            });
          } else {
            navigation.reset({
              index: 0,
              routes: [{ name: 'Dashboard' }],
            });
          }
        } else {
          navigation.reset({
            index: 0,
            routes: [{ name: 'Login' }],
          });
        }
      })
      .catch(() => {
        if (!isMounted) return;
        navigation.reset({
          index: 0,
          routes: [{ name: 'Login' }],
        });
      });

    return () => {
      isMounted = false;
    };
  }, [navigation]);

  return (
    <View style={styles.container}>
      <StatusBar hidden={false} barStyle="light-content" backgroundColor="#031635" />
      <View style={styles.content}>
        <Image source={NIRIKSHA_LOGO_ASSET} style={styles.logo} resizeMode="contain" />
        <Text style={styles.title}>NiriKsha</Text>
        <Text style={styles.subtitle}>Department of Consumer Affairs • Legal Metrology</Text>
        <ActivityIndicator size="small" color="#ffffff" style={{ marginTop: 24 }} />
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#031635',
    justifyContent: 'center',
    alignItems: 'center',
  },
  content: {
    alignItems: 'center',
    paddingHorizontal: 24,
  },
  logo: {
    width: 120,
    height: 120,
    marginBottom: 20,
  },
  title: {
    color: '#ffffff',
    fontSize: 28,
    fontWeight: '800',
    letterSpacing: 1.5,
  },
  subtitle: {
    color: 'rgba(255, 255, 255, 0.75)',
    fontSize: 13,
    fontWeight: '500',
    marginTop: 8,
    textAlign: 'center',
  },
});
