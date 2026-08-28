import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const TOKEN_KEY = 'legal_metrology_jwt_token';
const PROFILE_KEY = 'legal_metrology_officer_profile';

let memoryToken: string | null = null;
let memoryProfile: any = null;

export const authStorage = {
  async saveToken(token: string): Promise<void> {
    memoryToken = token;
    try {
      if (Platform.OS !== 'web') {
        await SecureStore.setItemAsync(TOKEN_KEY, token);
      }
    } catch (e) {
      console.warn('SecureStore saveToken fallback:', e);
    }
  },

  async getToken(): Promise<string | null> {
    if (memoryToken) return memoryToken;
    try {
      if (Platform.OS !== 'web') {
        const token = await SecureStore.getItemAsync(TOKEN_KEY);
        memoryToken = token;
        return token;
      }
    } catch (e) {
      console.warn('SecureStore getToken fallback:', e);
    }
    return memoryToken;
  },

  async saveProfile(profile: any): Promise<void> {
    memoryProfile = profile;
    try {
      if (Platform.OS !== 'web') {
        await SecureStore.setItemAsync(PROFILE_KEY, JSON.stringify(profile));
      }
    } catch (e) {
      console.warn('SecureStore saveProfile fallback:', e);
    }
  },

  async getProfile(): Promise<any | null> {
    if (memoryProfile) return memoryProfile;
    try {
      if (Platform.OS !== 'web') {
        const raw = await SecureStore.getItemAsync(PROFILE_KEY);
        if (raw) {
          memoryProfile = JSON.parse(raw);
          return memoryProfile;
        }
      }
    } catch (e) {
      console.warn('SecureStore getProfile fallback:', e);
    }
    return memoryProfile;
  },

  async clear(): Promise<void> {
    memoryToken = null;
    memoryProfile = null;
    try {
      if (Platform.OS !== 'web') {
        await SecureStore.deleteItemAsync(TOKEN_KEY);
        await SecureStore.deleteItemAsync(PROFILE_KEY);
      }
    } catch (e) {
      console.warn('SecureStore clear fallback:', e);
    }
  }
};
