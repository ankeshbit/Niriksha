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
      if (Platform.OS === 'web') {
        if (typeof localStorage !== 'undefined') {
          localStorage.setItem(TOKEN_KEY, token);
        }
      } else {
        await SecureStore.setItemAsync(TOKEN_KEY, token);
      }
    } catch (e) {
      console.warn('authStorage saveToken fallback:', e);
    }
  },

  async getToken(): Promise<string | null> {
    if (memoryToken) return memoryToken;
    try {
      if (Platform.OS === 'web') {
        if (typeof localStorage !== 'undefined') {
          const webToken = localStorage.getItem(TOKEN_KEY);
          if (webToken) {
            memoryToken = webToken;
            return webToken;
          }
        }
      } else {
        const token = await SecureStore.getItemAsync(TOKEN_KEY);
        if (token) {
          memoryToken = token;
          return token;
        }
      }
    } catch (e) {
      console.warn('authStorage getToken fallback:', e);
    }
    return memoryToken;
  },

  async saveProfile(profile: any): Promise<void> {
    memoryProfile = profile;
    try {
      const jsonStr = JSON.stringify(profile);
      if (Platform.OS === 'web') {
        if (typeof localStorage !== 'undefined') {
          localStorage.setItem(PROFILE_KEY, jsonStr);
        }
      } else {
        await SecureStore.setItemAsync(PROFILE_KEY, jsonStr);
      }
    } catch (e) {
      console.warn('authStorage saveProfile fallback:', e);
    }
  },

  async getProfile(): Promise<any | null> {
    if (memoryProfile) return memoryProfile;
    try {
      if (Platform.OS === 'web') {
        if (typeof localStorage !== 'undefined') {
          const raw = localStorage.getItem(PROFILE_KEY);
          if (raw) {
            memoryProfile = JSON.parse(raw);
            return memoryProfile;
          }
        }
      } else {
        const raw = await SecureStore.getItemAsync(PROFILE_KEY);
        if (raw) {
          memoryProfile = JSON.parse(raw);
          return memoryProfile;
        }
      }
    } catch (e) {
      console.warn('authStorage getProfile fallback:', e);
    }
    return memoryProfile;
  },

  async clear(): Promise<void> {
    memoryToken = null;
    memoryProfile = null;
    try {
      if (Platform.OS === 'web') {
        if (typeof localStorage !== 'undefined') {
          localStorage.removeItem(TOKEN_KEY);
          localStorage.removeItem(PROFILE_KEY);
        }
      } else {
        await SecureStore.deleteItemAsync(TOKEN_KEY);
        await SecureStore.deleteItemAsync(PROFILE_KEY);
      }
    } catch (e) {
      console.warn('authStorage clear fallback:', e);
    }
  }
};
