import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  Platform,
} from 'react-native';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { AppHeader } from '../components/AppHeader';
import { BottomNav } from '../components/BottomNav';
import { MetricCard } from '../components/MetricCard';
import { StatusBadge } from '../components/StatusBadge';
import { api } from '../services/api';
import { authStorage } from '../services/authStorage';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const DashboardScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [profile, setProfile] = useState<any>(null);
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadData = async () => {
    try {
      const [prof, dash] = await Promise.all([
        authStorage.getProfile(),
        api.getDashboard(),
      ]);
      setProfile(prof);
      setDashboardData(dash);
    } catch (err) {
      console.error('Failed to load dashboard:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useFocusEffect(
    useCallback(() => {
      loadData();
    }, [])
  );

  const onRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const todayStr = new Date().toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });

  return (
    <View style={styles.container}>
      <AppHeader
        title="LEGAL METROLOGY"
        subtitle="Department of Consumer Affairs (DoCA)"
        rightAction={{
          icon: 'add',
          label: 'NEW',
          onPress: () => navigation.navigate('NewInspection'),
        }}
      />

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        {/* Officer Welcome Banner */}
        <View style={styles.welcomeBanner}>
          <Text style={styles.greetingTitle}>
            Good morning, {profile?.full_name || 'Inspector'}
          </Text>
          <Text style={styles.greetingSubtitle}>
            ID: {profile?.officer_id || 'DOCA-INSP-842'} • {todayStr}
          </Text>
        </View>

        {loading ? (
          <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
        ) : (
          <>
            {/* 4 Metric Cards Grid (2x2) */}
            <View style={styles.metricsGrid}>
              <View style={styles.metricsRow}>
                <MetricCard
                  title="TOTAL INSPECTIONS"
                  count={dashboardData?.total_inspections ?? 0}
                  icon="assignment"
                  color={colors.primary}
                  bgColor={colors.surfaceContainerLow}
                />
                <MetricCard
                  title="NEEDS VERIFICATION"
                  count={dashboardData?.needs_manual_verification ?? 0}
                  icon="warning"
                  color={colors.statusAmberText}
                  bgColor={colors.statusAmberBg}
                />
              </View>

              <View style={styles.metricsRow}>
                <MetricCard
                  title="VERIFIED COMPLIANT"
                  count={dashboardData?.verified_inspections ?? 0}
                  icon="check-circle"
                  color={colors.statusGreenText}
                  bgColor={colors.statusGreenBg}
                />
                <MetricCard
                  title="POTENTIAL VIOLATIONS"
                  count={dashboardData?.potential_non_compliance ?? 0}
                  icon="error"
                  color={colors.statusRedText}
                  bgColor={colors.statusRedBg}
                />
              </View>
            </View>

            {/* Recent Inspections Table Card */}
            <View style={styles.recentCard}>
              <View style={styles.recentHeader}>
                <Text style={typography.sectionHeader}>Recent Inspections</Text>
                <TouchableOpacity onPress={() => navigation.navigate('ReportsList')}>
                  <Text style={styles.viewAllText}>View All →</Text>
                </TouchableOpacity>
              </View>

              {!dashboardData?.recent_inspections || dashboardData.recent_inspections.length === 0 ? (
                <View style={styles.emptyContainer}>
                  <Text style={typography.bodySm}>
                    No inspections recorded yet. Tap "+ NEW" to start.
                  </Text>
                </View>
              ) : (
                dashboardData.recent_inspections.map((item: any, idx: number) => {
                  const isLast = idx === dashboardData.recent_inspections.length - 1;
                  return (
                    <TouchableOpacity
                      key={item.id}
                      style={[styles.inspectionRow, !isLast && styles.rowBorder]}
                      onPress={() =>
                        navigation.navigate('Findings', {
                          inspectionId: item.id,
                          inspectionNumber: item.inspection_number,
                        })
                      }
                      activeOpacity={0.7}
                    >
                      <View style={styles.rowMain}>
                        <View style={styles.rowTopLine}>
                          <Text style={styles.inspNumber}>{item.inspection_number}</Text>
                          <StatusBadge status={item.overall_status || item.status} />
                        </View>
                        <Text style={styles.productName} numberOfLines={1}>
                          {item.product_name}
                        </Text>
                        <Text style={styles.locationText} numberOfLines={1}>
                          {item.location}
                        </Text>
                      </View>
                    </TouchableOpacity>
                  );
                })
              )}
            </View>
          </>
        )}
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
    gap: spacing.gutter,
  },
  welcomeBanner: {
    marginBottom: 4,
  },
  greetingTitle: {
    ...typography.headlineLg,
    color: colors.primary,
  },
  greetingSubtitle: {
    ...typography.bodySm,
    color: colors.onSurfaceVariant,
    marginTop: 2,
  },
  metricsGrid: {
    gap: spacing.stackMd,
  },
  metricsRow: {
    flexDirection: 'row',
    gap: spacing.stackMd,
  },
  recentCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    overflow: 'hidden',
  },
  recentHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.marginX,
    paddingVertical: spacing.stackMd,
    backgroundColor: colors.surfaceContainerLow,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  viewAllText: {
    ...typography.caption,
    color: colors.primary,
    fontWeight: '700',
  },
  emptyContainer: {
    padding: spacing.stackLg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  inspectionRow: {
    paddingHorizontal: spacing.marginX,
    paddingVertical: spacing.stackMd,
  },
  rowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  rowMain: {
    gap: 4,
  },
  rowTopLine: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  inspNumber: {
    ...typography.caption,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
    fontWeight: '700',
    color: colors.primary,
  },
  productName: {
    ...typography.bodyMdMedium,
    color: colors.onSurface,
  },
  locationText: {
    ...typography.bodySm,
    color: colors.onSurfaceVariant,
  },
});
