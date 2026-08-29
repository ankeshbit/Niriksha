import React from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  SafeAreaView,
  Alert,
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { BottomNav } from '../components/BottomNav';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const DraftOfflineScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();

  const handleRetryConnection = () => {
    Alert.alert('Network Sync', 'Checking connection to Legal Metrology Central Server...\n\nConnection restored.');
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        {/* Stitch TopAppBar Header */}
        <View style={styles.topHeader}>
          <TouchableOpacity
            style={styles.backButton}
            onPress={() => navigation.navigate('Dashboard')}
            activeOpacity={0.7}
          >
            <MaterialIcons name="arrow-back" size={24} color={colors.primary} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Legal Metrology</Text>
          <View style={styles.avatarCircle}>
            <MaterialIcons name="person" size={20} color={colors.primary} />
          </View>
        </View>

        {/* Warning Banner */}
        <View style={styles.warningBanner}>
          <MaterialIcons name="warning" size={18} color={colors.statusAmberText} />
          <Text style={styles.warningBannerText}>Connection Lost</Text>
        </View>

        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          {/* Header Text */}
          <Text style={styles.instructionText}>Your inspection has been saved as a local draft.</Text>

          {/* Central Card */}
          <View style={styles.centralCard}>
            <View style={styles.centralCardHeader}>
              <MaterialIcons name="content-paste" size={20} color={colors.onSurfaceVariant} />
              <Text style={styles.centralCardHeaderText}>DRAFT SAVED LOCALLY</Text>
            </View>

            <View style={styles.centralCardBody}>
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>ID</Text>
                <Text style={styles.infoValueBold}>LM-2026-00891</Text>
              </View>

              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>Product</Text>
                <Text style={styles.infoValueBold}>Premium Basmati Rice</Text>
              </View>

              <View style={styles.cardFooterRow}>
                <View style={styles.imagesSavedBox}>
                  <MaterialIcons name="image" size={14} color={colors.onSurfaceVariant} />
                  <Text style={styles.imagesSavedText}>2 images saved · 27 Aug 2026</Text>
                </View>

                <View style={styles.pendingBadge}>
                  <MaterialIcons
                    name="radio-button-checked"
                    size={14}
                    color={colors.statusAmberText}
                  />
                  <Text style={styles.pendingBadgeText}>DRAFT — Pending Sync</Text>
                </View>
              </View>
            </View>
          </View>

          {/* Checklist Card */}
          <View style={styles.checklistCard}>
            <Text style={styles.checklistTitle}>What was saved:</Text>

            <View style={styles.checklistItemsList}>
              <View style={styles.checkItemRow}>
                <MaterialIcons name="check-circle" size={18} color={colors.statusGreenText} />
                <Text style={styles.checkItemText}>Inspection details</Text>
              </View>

              <View style={styles.checkItemRow}>
                <MaterialIcons name="check-circle" size={18} color={colors.statusGreenText} />
                <Text style={styles.checkItemText}>2 package images (locally stored)</Text>
              </View>

              <View style={styles.checkItemRow}>
                <MaterialIcons name="cancel" size={18} color={colors.statusRedText} />
                <Text style={styles.checkItemText}>AI analysis not started (requires connection)</Text>
              </View>
            </View>
          </View>

          {/* Action Buttons */}
          <View style={styles.actionsContainer}>
            <TouchableOpacity
              style={styles.retryButton}
              onPress={handleRetryConnection}
              activeOpacity={0.85}
            >
              <MaterialIcons name="sync" size={18} color={colors.onPrimary} />
              <Text style={styles.retryButtonText}>Retry Connection</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.continueOfflineBtn}
              onPress={() => navigation.navigate('NewInspection')}
              activeOpacity={0.85}
            >
              <Text style={styles.continueOfflineText}>Continue Offline — Review Draft</Text>
            </TouchableOpacity>

            <Text style={styles.autoSyncNote}>
              Your data will sync automatically when the connection is restored.
            </Text>
          </View>
        </ScrollView>

        {/* Bottom Navigation */}
        <BottomNav />
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.background,
  },
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  topHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.surfaceContainerLowest,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    height: 56,
    paddingHorizontal: spacing.gutter,
  },
  backButton: {
    padding: 6,
    borderRadius: borderRadius.round,
  },
  headerTitle: {
    ...typography.headlineLg,
    fontSize: 18,
    fontWeight: '700',
    color: colors.primary,
  },
  avatarCircle: {
    width: 32,
    height: 32,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    backgroundColor: colors.surfaceContainerLow,
    alignItems: 'center',
    justifyContent: 'center',
  },
  warningBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.statusAmberBg,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    paddingHorizontal: spacing.gutter,
    paddingVertical: spacing.stackSm,
    gap: 8,
  },
  warningBannerText: {
    ...typography.bodySm,
    fontSize: 13,
    fontWeight: '600',
    color: colors.statusAmberText,
  },
  scrollContent: {
    paddingHorizontal: spacing.gutter,
    paddingTop: spacing.stackMd,
    paddingBottom: 90,
    gap: spacing.stackMd,
  },
  instructionText: {
    ...typography.bodyMd,
    fontSize: 14,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
  },
  centralCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    padding: spacing.gutter,
    gap: 12,
  },
  centralCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    paddingBottom: spacing.stackSm,
  },
  centralCardHeaderText: {
    ...typography.sectionHeader,
    fontSize: 14,
    color: colors.onSurface,
    fontWeight: '700',
  },
  centralCardBody: {
    gap: 8,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  infoLabel: {
    ...typography.bodyMd,
    fontSize: 13,
    color: colors.onSurfaceVariant,
  },
  infoValueBold: {
    ...typography.bodyMd,
    fontSize: 14,
    fontWeight: '600',
    color: colors.onSurface,
  },
  cardFooterRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
    marginTop: 4,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: colors.surfaceContainerHigh,
  },
  imagesSavedBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  imagesSavedText: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
  pendingBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.statusAmberBg,
    borderWidth: 1,
    borderColor: colors.statusAmberText,
    borderRadius: borderRadius.DEFAULT,
    paddingHorizontal: 8,
    paddingVertical: 2,
    gap: 4,
  },
  pendingBadgeText: {
    ...typography.labelCaps,
    fontSize: 10,
    fontWeight: '600',
    color: colors.statusAmberText,
  },
  checklistCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    padding: spacing.gutter,
    gap: 10,
  },
  checklistTitle: {
    ...typography.sectionHeader,
    fontSize: 14,
    color: colors.onSurface,
    fontWeight: '600',
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    paddingBottom: spacing.stackSm,
  },
  checklistItemsList: {
    gap: 10,
  },
  checkItemRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  checkItemText: {
    ...typography.bodySm,
    fontSize: 13,
    color: colors.onSurfaceVariant,
  },
  actionsContainer: {
    gap: 10,
    marginTop: 4,
  },
  retryButton: {
    backgroundColor: colors.primaryContainer,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: borderRadius.DEFAULT,
    gap: 8,
  },
  retryButtonText: {
    ...typography.sectionHeader,
    fontSize: 14,
    color: colors.onPrimary,
    fontWeight: '600',
  },
  continueOfflineBtn: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: colors.primaryContainer,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: borderRadius.DEFAULT,
  },
  continueOfflineText: {
    ...typography.sectionHeader,
    fontSize: 14,
    color: colors.primaryContainer,
    fontWeight: '600',
  },
  autoSyncNote: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
    marginTop: 4,
  },
});
