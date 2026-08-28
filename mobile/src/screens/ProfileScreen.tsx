import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { AppHeader } from '../components/AppHeader';
import { BottomNav } from '../components/BottomNav';
import { authStorage } from '../services/authStorage';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const ProfileScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [profile, setProfile] = useState<any>(null);

  useEffect(() => {
    authStorage.getProfile().then((prof) => {
      if (prof) setProfile(prof);
    });
  }, []);

  const handleSignOut = () => {
    Alert.alert('Sign Out', 'Are you sure you want to end your inspection session?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Sign Out',
        style: 'destructive',
        onPress: async () => {
          await authStorage.clear();
          navigation.reset({
            index: 0,
            routes: [{ name: 'Login' }],
          });
        },
      },
    ]);
  };

  return (
    <View style={styles.container}>
      <AppHeader
        title="OFFICER PROFILE"
        subtitle="Department of Consumer Affairs (DoCA)"
        showBack={false}
      />

      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Officer Credentials Card */}
        <View style={styles.card}>
          <View style={styles.badgeHeader}>
            <View style={styles.avatarCircle}>
              <MaterialIcons name="person" size={36} color={colors.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.officerName}>{profile?.full_name || 'Inspector Rajesh Sharma'}</Text>
              <Text style={styles.officerRole}>{profile?.designation || 'Senior Legal Metrology Inspector'}</Text>
              <Text style={styles.officerId}>ID: {profile?.officer_id || 'DOCA-INSP-842'}</Text>
            </View>
          </View>

          <View style={styles.divider} />

          <View style={styles.detailGrid}>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Department:</Text>
              <Text style={styles.detailValue}>Department of Consumer Affairs (DoCA)</Text>
            </View>

            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Ministry:</Text>
              <Text style={styles.detailValue}>Ministry of Consumer Affairs, Food & Public Distribution</Text>
            </View>

            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Jurisdiction Zone:</Text>
              <Text style={styles.detailValue}>{profile?.zone || 'Northern Zone - Delhi HQ'}</Text>
            </View>

            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Statutory Authority:</Text>
              <Text style={styles.detailValue}>Legal Metrology (Packaged Commodities) Rules, 2011</Text>
            </View>
          </View>
        </View>

        {/* Security & System Info Card */}
        <View style={styles.card}>
          <Text style={typography.sectionHeader}>System & Audit Integrity</Text>

          <View style={styles.infoRow}>
            <MaterialIcons name="security" size={18} color={colors.statusGreenText} />
            <Text style={styles.infoRowText}>JWT Bearer Session Active & Secure</Text>
          </View>

          <View style={styles.infoRow}>
            <MaterialIcons name="history" size={18} color={colors.primary} />
            <Text style={styles.infoRowText}>Immutable Audit Logging Enabled</Text>
          </View>

          <View style={styles.infoRow}>
            <MaterialIcons name="info" size={18} color={colors.secondary} />
            <Text style={styles.infoRowText}>SIH 2026 Legal Metrology Edition • v1.0.0</Text>
          </View>
        </View>

        {/* Sign Out Button */}
        <TouchableOpacity
          style={styles.signOutButton}
          onPress={handleSignOut}
          activeOpacity={0.85}
        >
          <MaterialIcons name="logout" size={18} color={colors.statusRedText} />
          <Text style={styles.signOutText}>Sign Out from Field Terminal</Text>
        </TouchableOpacity>
      </ScrollView>

      <BottomNav />
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
    paddingBottom: 24,
    gap: spacing.stackMd,
  },
  card: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.marginX,
    gap: spacing.stackSm,
  },
  badgeHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  avatarCircle: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    alignItems: 'center',
    justifyContent: 'center',
  },
  officerName: {
    ...typography.headlineLg,
    fontSize: 17,
    lineHeight: 22,
    color: colors.primary,
  },
  officerRole: {
    ...typography.bodySm,
    color: colors.onSurfaceVariant,
    marginTop: 2,
  },
  officerId: {
    ...typography.caption,
    fontWeight: '700',
    color: colors.primary,
    marginTop: 2,
  },
  divider: {
    height: 1,
    backgroundColor: colors.surfaceContainerHigh,
    marginVertical: 4,
  },
  detailGrid: {
    gap: 8,
  },
  detailRow: {
    gap: 2,
  },
  detailLabel: {
    ...typography.caption,
    fontSize: 10,
    fontWeight: '600',
    color: colors.onSurfaceVariant,
    textTransform: 'uppercase',
  },
  detailValue: {
    ...typography.bodySm,
    color: colors.onSurface,
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 4,
  },
  infoRowText: {
    ...typography.bodySm,
    color: colors.onSurface,
  },
  signOutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.statusRedBg,
    borderWidth: 1,
    borderColor: colors.statusRedText,
    borderRadius: borderRadius.lg,
    paddingVertical: 12,
    gap: 8,
    marginTop: 8,
  },
  signOutText: {
    ...typography.sectionHeader,
    fontSize: 14,
    color: colors.statusRedText,
  },
});
