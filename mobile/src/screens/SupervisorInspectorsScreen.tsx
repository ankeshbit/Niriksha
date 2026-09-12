import React, { useState, useEffect, useCallback } from 'react';
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
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const SupervisorInspectorsScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const insets = useSafeAreaInsets();
  const [inspectors, setInspectors] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchInspectors = useCallback(async (isRefresh = false) => {
    try {
      if (!isRefresh) setLoading(true);
      setError(null);
      const res: any = await api.getSupervisorInspectors();
      setInspectors(res.inspectors || []);
    } catch (err: any) {
      setError(err?.message || 'Failed to load inspector profiles.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchInspectors();
  }, [fetchInspectors]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchInspectors(true);
  };

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
      <View style={styles.container}>
        {/* Header */}
        <View style={styles.topHeader}>
          <TouchableOpacity
            style={styles.backButton}
            onPress={() => navigation.navigate('SupervisorDashboard')}
          >
            <MaterialIcons name="arrow-back" size={24} color={colors.onSurface} />
          </TouchableOpacity>
          <View style={styles.headerTitleContainer}>
            <Text style={styles.headerTitle}>Field Officers</Text>
            <Text style={styles.headerSub}>{inspectors.length} Registered Officers</Text>
          </View>
          <TouchableOpacity style={styles.refreshIcon} onPress={() => fetchInspectors()}>
            <MaterialIcons name="refresh" size={22} color={colors.primary} />
          </TouchableOpacity>
        </View>

        {loading && !refreshing ? (
          <View style={styles.centerContainer}>
            <ActivityIndicator size="large" color={colors.primary} />
            <Text style={styles.loadingText}>Fetching officer records...</Text>
          </View>
        ) : error ? (
          <View style={styles.centerContainer}>
            <MaterialIcons name="error-outline" size={44} color={colors.error} />
            <Text style={styles.errorTitle}>Could Not Load Inspectors</Text>
            <Text style={styles.errorMessage}>{error}</Text>
            <TouchableOpacity style={styles.retryBtn} onPress={() => fetchInspectors()}>
              <Text style={styles.retryBtnText}>Retry</Text>
            </TouchableOpacity>
          </View>
        ) : inspectors.length === 0 ? (
          <View style={styles.centerContainer}>
            <MaterialIcons name="groups" size={48} color={colors.outline} />
            <Text style={styles.emptyTitle}>No Field Inspectors Found</Text>
            <Text style={styles.emptySub}>No active inspector profiles in the database.</Text>
          </View>
        ) : (
          <ScrollView
            style={styles.listArea}
            contentContainerStyle={[
              styles.listContent,
              { paddingBottom: insets.bottom + BOTTOM_NAV_TAB_HEIGHT + 30 },
            ]}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={[colors.primary]} />}
          >
            {inspectors.map((insp) => (
              <View key={insp.inspector_id} style={styles.card}>
                <View style={styles.cardTop}>
                  <ProfileAvatar name={insp.full_name} size={42} />
                  <View style={styles.cardInfo}>
                    <Text style={styles.officerName}>{insp.full_name}</Text>
                    <Text style={styles.officerId}>{insp.officer_id} • {insp.zone}</Text>
                    <Text style={styles.designation}>{insp.designation}</Text>
                  </View>
                </View>

                {/* Metrics Badges Row */}
                <View style={styles.metricsRow}>
                  <View style={styles.metricBadge}>
                    <Text style={styles.metricVal}>{insp.total_inspections}</Text>
                    <Text style={styles.metricLabel}>Total</Text>
                  </View>
                  <View style={styles.metricBadge}>
                    <Text style={[styles.metricVal, { color: colors.statusGreenText }]}>
                      {insp.completed_inspections}
                    </Text>
                    <Text style={styles.metricLabel}>Done</Text>
                  </View>
                  <View style={styles.metricBadge}>
                    <Text style={[styles.metricVal, { color: colors.statusRedText }]}>
                      {insp.potential_non_compliance}
                    </Text>
                    <Text style={styles.metricLabel}>Violations</Text>
                  </View>
                  <View style={styles.metricBadge}>
                    <Text style={[styles.metricVal, { color: colors.statusAmberText }]}>
                      {insp.manual_verification_required}
                    </Text>
                    <Text style={styles.metricLabel}>Review</Text>
                  </View>
                  <View style={styles.metricBadge}>
                    <Text style={styles.metricVal}>{insp.reports_generated}</Text>
                    <Text style={styles.metricLabel}>Reports</Text>
                  </View>
                </View>

                {/* Contact & Action */}
                <View style={styles.cardFooter}>
                  <View style={styles.contactCol}>
                    {insp.email && <Text style={styles.contactText}>✉ {insp.email}</Text>}
                    {insp.phone && <Text style={styles.contactText}>📞 {insp.phone}</Text>}
                  </View>
                  <TouchableOpacity
                    style={styles.viewInspectionsBtn}
                    onPress={() =>
                      navigation.navigate('SupervisorAllInspections', {
                        inspectorIdFilter: insp.officer_id,
                      })
                    }
                  >
                    <Text style={styles.viewInspectionsBtnText}>View Scans</Text>
                    <MaterialIcons name="arrow-forward" size={14} color={colors.primary} />
                  </TouchableOpacity>
                </View>
              </View>
            ))}
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
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.outlineVariant,
  },
  backButton: {
    padding: 4,
    marginRight: spacing.sm,
  },
  headerTitleContainer: {
    flex: 1,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.onSurface,
  },
  headerSub: {
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
  refreshIcon: {
    padding: 4,
  },
  listArea: {
    flex: 1,
  },
  listContent: {
    padding: spacing.md,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.xl,
  },
  loadingText: {
    marginTop: spacing.md,
    fontSize: 13,
    color: colors.onSurfaceVariant,
  },
  errorTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.onSurface,
    marginTop: spacing.sm,
  },
  errorMessage: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
    marginTop: 4,
    marginBottom: spacing.md,
  },
  retryBtn: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.xs + 4,
    borderRadius: borderRadius.md,
  },
  retryBtnText: {
    color: '#FFFFFF',
    fontWeight: '600',
    fontSize: 13,
  },
  emptyTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.onSurface,
    marginTop: spacing.sm,
  },
  emptySub: {
    fontSize: 12,
    color: colors.onSurfaceVariant,
    marginTop: 2,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    padding: spacing.md,
    marginBottom: spacing.sm + 4,
    borderWidth: 1,
    borderColor: colors.outlineVariant,
  },
  cardTop: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  cardInfo: {
    flex: 1,
    marginLeft: spacing.sm + 4,
  },
  officerName: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.onSurface,
  },
  officerId: {
    fontSize: 12,
    color: colors.primary,
    fontWeight: '600',
    marginTop: 1,
  },
  designation: {
    fontSize: 11,
    color: colors.onSurfaceVariant,
    marginTop: 1,
  },
  metricsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: colors.surfaceContainerLow,
    borderRadius: borderRadius.sm,
    padding: spacing.sm,
    marginVertical: spacing.xs,
  },
  metricBadge: {
    alignItems: 'center',
    flex: 1,
  },
  metricVal: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.onSurface,
  },
  metricLabel: {
    fontSize: 10,
    color: colors.onSurfaceVariant,
    marginTop: 2,
  },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.sm,
    paddingTop: spacing.xs + 2,
    borderTopWidth: 1,
    borderTopColor: colors.outlineVariant,
  },
  contactCol: {
    flex: 1,
  },
  contactText: {
    fontSize: 11,
    color: colors.onSurfaceVariant,
    marginBottom: 2,
  },
  viewInspectionsBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#EEF2FF',
    paddingHorizontal: spacing.sm + 4,
    paddingVertical: spacing.xs + 2,
    borderRadius: borderRadius.full,
    gap: 4,
  },
  viewInspectionsBtnText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.primary,
  },
});
