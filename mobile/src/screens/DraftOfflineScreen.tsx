import React from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { AppHeader } from '../components/AppHeader';
import { BottomNav } from '../components/BottomNav';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const DraftOfflineScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();

  return (
    <View style={styles.container}>
      <AppHeader
        title="OFFLINE DRAFTS"
        subtitle="Department of Consumer Affairs (DoCA)"
        showBack={false}
      />

      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Offline Status Card */}
        <View style={styles.statusCard}>
          <MaterialIcons name="cloud-off" size={24} color={colors.statusAmberText} />
          <View style={{ flex: 1 }}>
            <Text style={styles.statusTitle}>Offline Field Resilience</Text>
            <Text style={styles.statusSubtext}>
              All inspection drafts, captured photos, and corrections are queued securely in local storage when network is offline.
            </Text>
          </View>
        </View>

        {/* Sync Guidance Card */}
        <View style={styles.card}>
          <Text style={typography.sectionHeader}>Offline Sync Protocol</Text>
          <Text style={typography.bodySm}>
            When performing market inspections in areas with poor cellular reception (e.g. underground wholesale mandis), the application persists your form data locally.
          </Text>

          <View style={styles.stepItem}>
            <MaterialIcons name="camera-alt" size={16} color={colors.primary} />
            <Text style={styles.stepText}>1. Capture package label photos offline</Text>
          </View>

          <View style={styles.stepItem}>
            <MaterialIcons name="edit" size={16} color={colors.primary} />
            <Text style={styles.stepText}>2. Record physical observations & batch details</Text>
          </View>

          <View style={styles.stepItem}>
            <MaterialIcons name="sync" size={16} color={colors.primary} />
            <Text style={styles.stepText}>3. Auto-sync with DoCA servers once connected</Text>
          </View>
        </View>

        {/* New Inspection Action */}
        <TouchableOpacity
          style={styles.newButton}
          onPress={() => navigation.navigate('NewInspection')}
          activeOpacity={0.85}
        >
          <MaterialIcons name="add" size={20} color={colors.onPrimary} />
          <Text style={styles.newButtonText}>Start New Field Inspection</Text>
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
  statusCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.statusAmberBg,
    borderWidth: 1,
    borderColor: colors.statusAmberText,
    borderRadius: borderRadius.lg,
    padding: spacing.marginX,
    gap: 12,
  },
  statusTitle: {
    ...typography.bodyMdMedium,
    color: colors.statusAmberText,
    fontWeight: '700',
  },
  statusSubtext: {
    ...typography.caption,
    color: colors.statusAmberText,
    marginTop: 2,
  },
  card: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.marginX,
    gap: spacing.stackSm,
  },
  stepItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 4,
  },
  stepText: {
    ...typography.bodySm,
    color: colors.onSurface,
  },
  newButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.primary,
    paddingVertical: 14,
    borderRadius: borderRadius.lg,
    gap: 6,
    marginTop: 8,
  },
  newButtonText: {
    ...typography.sectionHeader,
    color: colors.onPrimary,
  },
});
