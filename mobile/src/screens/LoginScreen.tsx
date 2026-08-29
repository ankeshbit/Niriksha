import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StatusBar,
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { api } from '../services/api';
import { authStorage } from '../services/authStorage';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const LoginScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [officerId, setOfficerId] = useState('DOCA-INSP-842');
  const [password, setPassword] = useState('admin123');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    authStorage.getToken().then((token) => {
      if (token) {
        navigation.replace('Dashboard');
      }
    });
  }, []);

  const handleLogin = async () => {
    if (!officerId.trim() || !password.trim()) {
      setErrorMessage('Please enter both Officer ID and password.');
      return;
    }

    setLoading(true);
    setErrorMessage(null);

    try {
      const data = await api.login({
        officer_id: officerId.trim(),
        password: password.trim(),
      });

      await authStorage.saveToken(data.access_token);
      await authStorage.saveProfile({
        officer_id: data.officer_id,
        full_name: data.full_name,
        designation: data.designation,
        zone: data.zone,
      });

      navigation.replace('Dashboard');
    } catch (err: any) {
      setErrorMessage(err.message || 'Invalid Inspector ID or password. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={styles.container}
    >
      <StatusBar barStyle="dark-content" backgroundColor={colors.surface} />
      <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
        <View style={styles.card}>
          {/* Header Section */}
          <View style={styles.headerSection}>
            <MaterialIcons
              name="verified-user"
              size={48}
              color={colors.primary}
              style={styles.logoIcon}
            />
            <Text style={styles.titleText}>LEGAL METROLOGY</Text>
            <Text style={styles.subtitleText}>AI-Assisted Legal Metrology Inspection</Text>
          </View>

          {/* Form Section */}
          <View style={styles.formSection}>
            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Inspector ID / Username</Text>
              <TextInput
                style={styles.textInput}
                value={officerId}
                onChangeText={(text) => {
                  setOfficerId(text);
                  if (errorMessage) setErrorMessage(null);
                }}
                placeholder="DOCA-INSP-842"
                placeholderTextColor={colors.outline}
                autoCapitalize="characters"
              />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Password</Text>
              <View style={styles.passwordContainer}>
                <TextInput
                  style={[styles.textInput, styles.passwordInput]}
                  value={password}
                  onChangeText={(text) => {
                    setPassword(text);
                    if (errorMessage) setErrorMessage(null);
                  }}
                  placeholder="••••••••"
                  placeholderTextColor={colors.outline}
                  secureTextEntry={!showPassword}
                />
                <TouchableOpacity
                  style={styles.eyeIcon}
                  onPress={() => setShowPassword(!showPassword)}
                  hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                >
                  <MaterialIcons
                    name={showPassword ? 'visibility-off' : 'visibility'}
                    size={20}
                    color={colors.onSurfaceVariant}
                  />
                </TouchableOpacity>
              </View>
            </View>

            {/* Error Message Banner */}
            {errorMessage ? (
              <View style={styles.errorBanner}>
                <MaterialIcons name="error" size={18} color={colors.statusRedText} />
                <Text style={styles.errorText}>{errorMessage}</Text>
              </View>
            ) : null}

            {/* Submit Button */}
            <TouchableOpacity
              style={styles.submitButton}
              onPress={handleLogin}
              disabled={loading}
              activeOpacity={0.85}
            >
              {loading ? (
                <ActivityIndicator size="small" color={colors.onPrimary} />
              ) : (
                <View style={styles.buttonContent}>
                  <Text style={styles.submitButtonText}>Sign In</Text>
                  <MaterialIcons name="login" size={18} color={colors.onPrimary} style={{ marginLeft: 6 }} />
                </View>
              )}
            </TouchableOpacity>
          </View>
        </View>

        {/* Stitch Footer */}
        <View style={styles.footerSection}>
          <View style={styles.footerLockRow}>
            <MaterialIcons name="lock" size={16} color={colors.onSurfaceVariant} />
            <Text style={styles.footerLockText}>Authorized inspection personnel only</Text>
          </View>
          <Text style={styles.footerPrototypeText}>Smart India Hackathon 2026 Prototype</Text>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.surface,
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.gutter,
  },
  card: {
    width: '100%',
    maxWidth: 400,
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    overflow: 'hidden',
  },
  headerSection: {
    alignItems: 'center',
    paddingHorizontal: spacing.marginX,
    paddingTop: spacing.stackMd,
    paddingBottom: spacing.stackSm,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  logoIcon: {
    marginBottom: spacing.stackSm,
  },
  titleText: {
    ...typography.headlineLg,
    fontSize: 20,
    lineHeight: 28,
    fontWeight: '700',
    color: colors.primary,
    marginBottom: spacing.tight,
  },
  subtitleText: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.onSurfaceVariant,
  },
  formSection: {
    padding: spacing.marginX,
    gap: spacing.stackMd,
  },
  inputGroup: {
    gap: spacing.tight,
  },
  inputLabel: {
    ...typography.labelCaps,
    fontSize: 12,
    lineHeight: 16,
    color: colors.onSurfaceVariant,
  },
  textInput: {
    backgroundColor: colors.surfaceBright,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    paddingHorizontal: 12,
    paddingVertical: 8,
    ...typography.bodyMd,
    color: colors.onSurface,
  },
  passwordContainer: {
    position: 'relative',
    justifyContent: 'center',
  },
  passwordInput: {
    paddingRight: 40,
  },
  eyeIcon: {
    position: 'absolute',
    right: 12,
  },
  errorBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.statusRedBg,
    borderWidth: 1,
    borderColor: 'rgba(183, 28, 28, 0.2)',
    borderRadius: borderRadius.lg,
    padding: 10,
    gap: 6,
  },
  errorText: {
    ...typography.bodySm,
    color: colors.statusRedText,
    flex: 1,
  },
  submitButton: {
    backgroundColor: colors.primary,
    paddingVertical: 10,
    borderRadius: borderRadius.lg,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.tight,
  },
  buttonContent: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  submitButtonText: {
    ...typography.sectionHeader,
    fontSize: 16,
    lineHeight: 24,
    color: colors.onPrimary,
  },
  footerSection: {
    marginTop: spacing.stackMd,
    alignItems: 'center',
    gap: spacing.tight,
  },
  footerLockRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.tight,
  },
  footerLockText: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
  },
  footerPrototypeText: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
  },
});
