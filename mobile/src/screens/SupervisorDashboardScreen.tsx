import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { BottomNav, BOTTOM_NAV_TAB_HEIGHT } from '../components/BottomNav';
import { ProfileAvatar } from '../components/ProfileAvatar';
import { api } from '../services/api';
import { authStorage } from '../services/authStorage';
import { getTimeBasedGreeting } from '../services/dateUtils';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const SupervisorDashboardScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const insets = useSafeAreaInsets();
  const [profile, setProfile] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadData = useCallback(async (isRefresh = false) => {
    try {
      if (!isRefresh) setLoading(true);
      setError(null);
      const [prof, dashData] = await Promise.all([
        authStorage.getProfile(),
        api.getSupervisorDashboard(),
      ]);
      setProfile(prof);
      setData(dashData);
    } catch (err: any) {
      setError(err?.message || 'Unable to connect to server. Please check backend status.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      loadData();
    }, [loadData])
  );

  const onRefresh = () => {
    setRefreshing(true);
    loadData(true);
  };

  const greeting = getTimeBasedGreeting();
  const supervisorName = profile?.full_name || 'Supervisor';

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
      <View style={styles.container}>
        {/* Header */}
        <View style={styles.topHeader}>
          <View style={styles.headerLeft}>
            <View style={styles.badgeRow}>
              <View style={styles.supervisorBadge}>
                <MaterialIcons name="security" size={14} color="#FFFFFF" />
                <Text style={styles.supervisorBadgeText}>SUPERVISOR</Text>
              </View>
              <Text style={styles.officerIdText}>{profile?.officer_id || 'DOCA-SUP-101'}</Text>
            </View>
            <Text style={styles.greetingText}>{greeting}, {supervisorName}</Text>
            <Text style={styles.zoneText}>{profile?.zone || 'Central HQ'} • {profile?.designation || 'Supervisory Officer'}</Text>
          </View>
          <TouchableOpacity
            onPress={() => navigation.navigate('Profile')}
            activeOpacity={0.8}
            style={styles.avatarButton}
          >
            <ProfileAvatar name={supervisorName} size={42} />
          </TouchableOpacity>
        </View>

        {loading ? (
          <View style={styles.centerContainer}>
            <ActivityIndicator size="large" color={colors.primary} />
            <Text style={styles.loadingText}>Loading management intelligence...</Text>
          </View>
        ) : error ? (
          <View style={styles.centerContainer}>
            <MaterialIcons name="cloud-off" size={48} color={colors.error} />
            <Text style={styles.errorTitle}>Management Data Unavailable</Text>
            <Text style={styles.errorMessage}>{error}</Text>
            <TouchableOpacity style={styles.retryButton} onPress={() => loadData()}>
              <MaterialIcons name="refresh" size={20} color="#FFFFFF" />
              <Text style={styles.retryButtonText}>Retry</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <ScrollView
            style={styles.scrollArea}
            contentContainerStyle={[
              styles.scrollContent,
              { paddingBottom: insets.bottom + BOTTOM_NAV_TAB_HEIGHT + 24 },
            ]}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={[colors.primary]} />}
          >
            {/* Quick Action Banner */}
            <View style={styles.actionBanner}>
              <View style={styles.actionBannerLeft}>
                <Text style={styles.actionBannerTitle}>Surveillance Overview</Text>
                <Text style={styles.actionBannerSubtitle}>
                  Managing across {data?.active_inspectors_count ?? 0} field officers
                </Text>
              </View>
              <TouchableOpacity
                style={styles.viewAllButton}
                onPress={() => navigation.navigate('SupervisorAllInspections')}
              >
                <Text style={styles.viewAllButtonText}>All Inspections</Text>
                <MaterialIcons name="arrow-forward" size={16} color={colors.primary} />
              </TouchableOpacity>
            </View>

            {/* KPI Grid */}
            <Text style={styles.sectionHeader}>Enforcement Key Metrics</Text>
            <View style={styles.kpiGrid}>
              <View style={[styles.kpiCard, { borderLeftColor: colors.primary, borderLeftWidth: 4 }]}>
                <Text style={styles.kpiLabel}>Total Scanned</Text>
                <Text style={styles.kpiValue}>{data?.total_inspections ?? 0}</Text>
                <Text style={styles.kpiSub}>All field officers</Text>
              </View>

              <View style={[styles.kpiCard, { borderLeftColor: '#0D9488', borderLeftWidth: 4 }]}>
                <Text style={styles.kpiLabel}>Today's Scans</Text>
                <Text style={styles.kpiValue}>{data?.today_inspections ?? 0}</Text>
                <Text style={styles.kpiSub}>Active today</Text>
              </View>

              <View style={[styles.kpiCard, { borderLeftColor: colors.statusGreenText, borderLeftWidth: 4 }]}>
                <Text style={styles.kpiLabel}>Completed</Text>
                <Text style={styles.kpiValue}>{data?.completed_inspections ?? 0}</Text>
                <Text style={styles.kpiSub}>Finalized inspections</Text>
              </View>

              <View style={[styles.kpiCard, { borderLeftColor: colors.statusRedText, borderLeftWidth: 4 }]}>
                <Text style={styles.kpiLabel}>Non-Compliance</Text>
                <Text style={[styles.kpiValue, { color: colors.statusRedText }]}>
                  {data?.potential_non_compliance ?? 0}
                </Text>
                <Text style={styles.kpiSub}>Potential violations</Text>
              </View>

              <View style={[styles.kpiCard, { borderLeftColor: colors.statusAmberText, borderLeftWidth: 4 }]}>
                <Text style={styles.kpiLabel}>Needs Review</Text>
                <Text style={[styles.kpiValue, { color: colors.statusAmberText }]}>
                  {data?.manual_verification_required ?? 0}
                </Text>
                <Text style={styles.kpiSub}>Manual verification</Text>
              </View>

              <View style={[styles.kpiCard, { borderLeftColor: '#6366F1', borderLeftWidth: 4 }]}>
                <Text style={styles.kpiLabel}>Reports Issued</Text>
                <Text style={styles.kpiValue}>{data?.reports_generated ?? 0}</Text>
                <Text style={styles.kpiSub}>Certified reports</Text>
              </View>
            </View>

            {/* Quick Links Row */}
            <View style={styles.quickLinksRow}>
              <TouchableOpacity
                style={styles.quickLinkCard}
                onPress={() => navigation.navigate('SupervisorInspectors')}
              >
                <View style={[styles.quickLinkIcon, { backgroundColor: '#EEF2FF' }]}>
                  <MaterialIcons name="groups" size={24} color="#4F46E5" />
                </View>
                <View style={styles.quickLinkInfo}>
                  <Text style={styles.quickLinkTitle}>Inspector Management</Text>
                  <Text style={styles.quickLinkSub}>Performance metrics across all field officers</Text>
                </View>
                <MaterialIcons name="chevron-right" size={24} color={colors.onSurfaceVariant} />
              </TouchableOpacity>
            </View>

            {/* Recent Submissions */}
            <View style={styles.sectionRow}>
              <Text style={styles.sectionHeader}>Recent Field Submissions</Text>
              <TouchableOpacity onPress={() => navigation.navigate('SupervisorAllInspections')}>
                <Text style={styles.seeAllText}>See all ({data?.total_inspections ?? 0})</Text>
              </TouchableOpacity>
            </View>

            {data?.recent_submissions && data.recent_submissions.length > 0 ? (
              data.recent_submissions.map((item: any) => (
                <TouchableOpacity
                  key={item.id}
                  style={styles.recentCard}
                  activeOpacity={0.7}
                  onPress={() =>
                    navigation.navigate('SupervisorInspectionDetail', {
                      inspectionId: item.id,
                      inspectionNumber: item.inspection_number,
                    })
                  }
                >
                  <View style={styles.recentCardHeader}>
                    <Text style={styles.recentInspNum}>{item.inspection_number}</Text>
                    <View
                      style={[
                        styles.statusPill,
                        item.overall_status === 'POTENTIAL_NON_COMPLIANCE'
                          ? styles.statusPillRed
                          : item.overall_status === 'NO_POTENTIAL_VIOLATIONS'
                          ? styles.statusPillGreen
                          : styles.statusPillAmber,
                      ]}
                    >
                      <Text
                        style={[
                          styles.statusPillText,
                          item.overall_status === 'POTENTIAL_NON_COMPLIANCE'
                            ? styles.statusTextRed
                            : item.overall_status === 'NO_POTENTIAL_VIOLATIONS'
                            ? styles.statusTextGreen
                            : styles.statusTextAmber,
                        ]}
                      >
                        {item.overall_status || item.status}
                      </Text>
                    </View>
                  </View>
                  <Text style={styles.recentProdName}>{item.product_name}</Text>
                  <View style={styles.recentMetaRow}>
                    <View style={styles.recentMetaItem}>
                      <MaterialIcons name="place" size={14} color={colors.onSurfaceVariant} />
                      <Text style={styles.recentMetaText}>{item.location}</Text>
                    </View>
                    <View style={styles.recentMetaItem}>
                      <MaterialIcons name="schedule" size={14} color={colors.onSurfaceVariant} />
                      <Text style={styles.recentMetaText}>
                        {new Date(item.created_at).toLocaleDateString('en-IN', {
                          month: 'short',
                          day: 'numeric',
                        })}
                      </Text>
                    </View>
                  </View>
                </TouchableOpacity>
              ))
            ) : (
              <View style={styles.emptyCard}>
                <MaterialIcons name="inbox" size={36} color={colors.outline} />
                <Text style={styles.emptyText}>No field inspections recorded yet.</Text>
              </View>
            )}
          </ScrollView>
        )}

        <BottomNav />
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
    backgroundColor: colors.surfaceContainerLowest,
  },
  topHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.outlineVariant,
  },
  headerLeft: {
    flex: 1,
  },
  badgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 4,
  },
  supervisorBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#7C3AED',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: borderRadius.full,
    gap: 4,
  },
  supervisorBadgeText: {
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  officerIdText: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    fontWeight: '600',
  },
  greetingText: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.onSurface,
  },
  zoneText: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
  },
  avatarButton: {
    padding: 2,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.xl,
  },
  loadingText: {
    marginTop: spacing.md,
    fontSize: 14,
    color: colors.onSurfaceVariant,
  },
  errorTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.onSurface,
    marginTop: spacing.md,
  },
  errorMessage: {
    fontSize: 13,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
    marginTop: 6,
    marginBottom: spacing.lg,
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.md,
    gap: 6,
  },
  retryButtonText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '600',
  },
  scrollArea: {
    flex: 1,
  },
  scrollContent: {
    padding: spacing.md,
  },
  actionBanner: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#F5F3FF',
    borderWidth: 1,
    borderColor: '#DDD6FE',
    borderRadius: borderRadius.lg,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  actionBannerLeft: {
    flex: 1,
  },
  actionBannerTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: '#5B21B6',
  },
  actionBannerSubtitle: {
    fontSize: 12,
    color: '#6D28D9',
    marginTop: 2,
  },
  viewAllButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: spacing.sm + 4,
    paddingVertical: spacing.xs + 2,
    borderRadius: borderRadius.full,
    borderWidth: 1,
    borderColor: '#C4B5FD',
    gap: 4,
  },
  viewAllButtonText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.primary,
  },
  sectionHeader: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.onSurface,
    marginBottom: spacing.sm,
  },
  kpiGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  kpiCard: {
    width: '48%',
    backgroundColor: colors.surface,
    padding: spacing.md,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.outlineVariant,
  },
  kpiLabel: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    fontWeight: '500',
  },
  kpiValue: {
    fontSize: 24,
    fontWeight: '800',
    color: colors.onSurface,
    marginTop: 4,
  },
  kpiSub: {
    fontSize: 10,
    color: colors.onSurfaceVariant,
    marginTop: 2,
  },
  quickLinksRow: {
    marginBottom: spacing.md,
  },
  quickLinkCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    padding: spacing.md,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.outlineVariant,
  },
  quickLinkIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: spacing.md,
  },
  quickLinkInfo: {
    flex: 1,
  },
  quickLinkTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.onSurface,
  },
  quickLinkSub: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    marginTop: 2,
  },
  sectionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  seeAllText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.primary,
  },
  recentCard: {
    backgroundColor: colors.surface,
    padding: spacing.md,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.outlineVariant,
    marginBottom: spacing.sm,
  },
  recentCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  recentInspNum: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.primary,
  },
  recentProdName: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.onSurface,
    marginBottom: 8,
  },
  recentMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  recentMetaItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  recentMetaText: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
  },
  statusPill: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: borderRadius.full,
  },
  statusPillGreen: {
    backgroundColor: colors.statusGreenBg,
  },
  statusPillRed: {
    backgroundColor: colors.statusRedBg,
  },
  statusPillAmber: {
    backgroundColor: colors.statusAmberBg,
  },
  statusPillText: {
    fontSize: 10,
    fontWeight: '700',
  },
  statusTextGreen: {
    color: colors.statusGreenText,
  },
  statusTextRed: {
    color: colors.statusRedText,
  },
  statusTextAmber: {
    color: colors.statusAmberText,
  },
  emptyCard: {
    backgroundColor: colors.surface,
    padding: spacing.xl,
    borderRadius: borderRadius.md,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.outlineVariant,
  },
  emptyText: {
    fontSize: 13,
    color: colors.onSurfaceVariant,
    marginTop: spacing.sm,
  },
});
