import React, { useState, useCallback } from 'react';
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
import { SafeAreaView } from 'react-native-safe-area-context';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
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

// Stitch Filter Chip Definitions
interface FilterChip {
  id: string;
  label: string;
  bgColor: string;
  borderColor: string;
  textColor: string;
  matcher?: (item: any) => boolean;
}

const FILTER_CHIPS: FilterChip[] = [
  {
    id: 'draft',
    label: 'Draft',
    bgColor: colors.surfaceContainerLowest,
    borderColor: colors.borderSubtle,
    textColor: colors.onSurfaceVariant,
    matcher: (item) => (item.status || '').toUpperCase() === 'DRAFT',
  },
  {
    id: 'processing',
    label: 'Processing',
    bgColor: colors.primaryContainer,
    borderColor: colors.primary,
    textColor: colors.onPrimary,
    matcher: (item) =>
      ['IMAGES_UPLOADED', 'OCR_PROCESSING', 'EXTRACTION_COMPLETE', 'PROCESSING'].includes(
        (item.status || '').toUpperCase()
      ),
  },
  {
    id: 'analysis_complete',
    label: 'Analysis Complete',
    bgColor: colors.statusGreenBg,
    borderColor: colors.statusGreenText,
    textColor: colors.statusGreenText,
    matcher: (item) =>
      ['RULE_EVALUATION_COMPLETE', 'COMPLETED', 'ANALYSIS_COMPLETE', 'VERIFIED_COMPLIANT', 'NO_POTENTIAL_VIOLATIONS', 'PASS'].includes(
        (item.status || '').toUpperCase()
      ) ||
      ['VERIFIED_COMPLIANT', 'NO_POTENTIAL_VIOLATIONS', 'PASS', 'COMPLETED'].includes(
        (item.overall_status || '').toUpperCase()
      ),
  },
  {
    id: 'needs_manual_verification',
    label: 'Needs Manual Verification',
    bgColor: colors.statusAmberBg,
    borderColor: colors.statusAmberText,
    textColor: colors.statusAmberText,
    matcher: (item) =>
      ['NEEDS_MANUAL_VERIFICATION', 'WARNING'].includes((item.overall_status || '').toUpperCase()),
  },
  {
    id: 'no_violations',
    label: 'No Violations',
    bgColor: colors.statusGreenBg,
    borderColor: colors.statusGreenText,
    textColor: colors.statusGreenText,
    matcher: (item) =>
      ['NO_POTENTIAL_VIOLATIONS', 'VERIFIED_COMPLIANT', 'PASS'].includes(
        (item.overall_status || '').toUpperCase()
      ),
  },
  {
    id: 'report_generated',
    label: 'Report Generated',
    bgColor: colors.secondaryContainer,
    borderColor: colors.primary,
    textColor: colors.primary,
    matcher: (item) =>
      ['FINALIZED', 'COMPLETED', 'REPORT_GENERATED'].includes((item.status || '').toUpperCase()) ||
      ['FINALIZED', 'COMPLETED', 'REPORT_GENERATED'].includes((item.overall_status || '').toUpperCase()),
  },
  {
    id: 'insufficient_evidence',
    label: 'Insufficient Evidence',
    bgColor: colors.surfaceContainerHighest,
    borderColor: colors.borderSubtle,
    textColor: colors.onSurface,
    matcher: (item) => (item.overall_status || '').toUpperCase() === 'INSUFFICIENT_EVIDENCE',
  },
];

export const DashboardScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const insets = useSafeAreaInsets();
  const [profile, setProfile] = useState<any>(null);
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [inspections, setInspections] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedChipId, setSelectedChipId] = useState<string | null>(null);
  const [currentDate, setCurrentDate] = useState(() => new Date());

  const loadData = async () => {
    try {
      const [prof, dash, list] = await Promise.all([
        authStorage.getProfile(),
        api.getDashboard(),
        api.listInspections({ limit: 100 }),
      ]);
      setProfile(prof);
      setDashboardData(dash);
      setInspections(list || []);
    } catch (err) {
      console.error('Failed to load dashboard:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useFocusEffect(
    useCallback(() => {
      setCurrentDate(new Date());
      loadData();
    }, [])
  );

  const onRefresh = () => {
    setRefreshing(true);
    setCurrentDate(new Date());
    loadData();
  };

  const todayStr = currentDate.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });

  const formatCount = (val?: number) => {
    const num = val ?? 0;
    return num < 10 ? `0${num}` : `${num}`;
  };

  // Filter if chip is active
  const filteredInspections = selectedChipId
    ? inspections.filter((item: any) => {
      const chip = FILTER_CHIPS.find((c) => c.id === selectedChipId);
      return chip?.matcher ? chip.matcher(item) : true;
    })
    : inspections.slice(0, 5);

  const getStatusBadgeProps = (status?: string) => {
    if (status === 'POTENTIAL_NON_COMPLIANCE' || status === 'FAIL' || status === 'CONFIRMED') {
      return {
        label: 'Potential Non-Compliance Identified',
        bg: colors.statusRedBg,
        text: colors.statusRedText,
        border: colors.statusRedText,
      };
    }
    if (status === 'VERIFIED_COMPLIANT' || status === 'NO_POTENTIAL_VIOLATIONS' || status === 'PASS') {
      return {
        label: 'No Potential Violations Detected',
        bg: colors.statusGreenBg,
        text: colors.statusGreenText,
        border: colors.statusGreenText,
      };
    }
    if (status === 'NEEDS_MANUAL_VERIFICATION' || status === 'WARNING') {
      return {
        label: 'Needs Manual Verification',
        bg: colors.statusAmberBg,
        text: colors.statusAmberText,
        border: colors.statusAmberText,
      };
    }
    if (status === 'INSUFFICIENT_EVIDENCE') {
      return {
        label: 'Insufficient Evidence',
        bg: colors.surfaceContainerHighest,
        text: colors.onSurface,
        border: colors.borderSubtle,
      };
    }
    return {
      label: 'No Potential Violations Detected',
      bg: colors.statusGreenBg,
      text: colors.statusGreenText,
      border: colors.statusGreenText,
    };
  };

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
      <View style={styles.container}>
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={[
            styles.scrollContent,
            // Ensure content is not hidden behind BottomNav on any device.
            // BOTTOM_NAV_TAB_HEIGHT = visible row height; insets.bottom = system navigation area.
            { paddingBottom: BOTTOM_NAV_TAB_HEIGHT + Math.max(insets.bottom, 6) + 16 },
          ]}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
          showsVerticalScrollIndicator={false}
        >
          {/* Welcome Header */}
          <View style={styles.welcomeHeader}>
            <View style={styles.welcomeHeaderRow}>
              <View style={styles.welcomeHeaderTextCol}>
                <Text style={styles.welcomeGreeting}>
                  {`${getTimeBasedGreeting(currentDate)}, ${profile?.full_name || 'Inspector'}`}
                </Text>
                <Text style={styles.welcomeSubtext}>
                  ID: {profile?.officer_id || 'DOCA-INSP-842'} • {todayStr}
                </Text>
              </View>
              <TouchableOpacity
                onPress={() => navigation.navigate('Profile')}
                activeOpacity={0.7}
                accessibilityRole="button"
                accessibilityLabel="Navigate to Profile"
              >
                <ProfileAvatar size={36} />
              </TouchableOpacity>
            </View>
          </View>

          {loading ? (
            <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
          ) : (
            <>
              {/* Dashboard Grid: 2x2 Metric Cards */}
              <View style={styles.metricsGrid}>
                <View style={styles.metricsRow}>
                  {/* Metric 1: Total Inspections */}
                  <View style={styles.metricCard}>
                    <Text style={styles.metricLabelDefault}>Total Inspections</Text>
                    <Text style={styles.metricValuePrimary}>
                      {formatCount(dashboardData?.total_inspections ?? 0)}
                    </Text>
                  </View>

                  {/* Metric 2: Needs Manual Verification */}
                  <View style={styles.metricCard}>
                    <Text style={styles.metricLabelAmber}>Needs Manual Verification</Text>
                    <Text style={styles.metricValueAmber}>
                      {formatCount(dashboardData?.needs_manual_verification ?? 0)}
                    </Text>
                  </View>
                </View>

                <View style={styles.metricsRow}>
                  {/* Metric 3: Verified Inspections */}
                  <View style={styles.metricCard}>
                    <Text style={styles.metricLabelDefault}>Verified Inspections</Text>
                    <Text style={styles.metricValuePrimary}>
                      {formatCount(dashboardData?.verified_inspections ?? 0)}
                    </Text>
                  </View>

                  {/* Metric 4: Potential Non-Compliance */}
                  <View style={styles.metricCard}>
                    <Text style={styles.metricLabelRed}>Potential Non-Compliance</Text>
                    <Text style={styles.metricValueRed}>
                      {formatCount(dashboardData?.potential_non_compliance ?? 0)}
                    </Text>
                  </View>
                </View>
              </View>

              {/* Status Filter Chips Row */}
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={styles.chipsScrollContent}
                style={styles.chipsScroll}
              >
                {FILTER_CHIPS.map((chip) => {
                  const isSelected = selectedChipId === chip.id;
                  return (
                    <TouchableOpacity
                      key={chip.id}
                      style={[
                        styles.chipButton,
                        {
                          backgroundColor: isSelected ? colors.primary : chip.bgColor,
                          borderColor: isSelected ? colors.primary : chip.borderColor,
                          opacity: isSelected || selectedChipId === null ? 1 : 0.6,
                          transform: [{ scale: isSelected ? 1.03 : 1 }],
                        },
                      ]}
                      onPress={() => {
                        setSelectedChipId(selectedChipId === chip.id ? null : chip.id);
                      }}
                      activeOpacity={0.85}
                    >
                      <Text style={[styles.chipText, { color: isSelected ? '#ffffff' : chip.textColor }]}>
                        {chip.label}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </ScrollView>

              {/* Recent Inspections List */}
              <View style={styles.recentSection}>
                <Text style={styles.sectionTitle}>Recent Inspections</Text>
                <View style={styles.recentCard}>
                  {filteredInspections.length === 0 ? (
                    <View style={{ paddingVertical: 24, alignItems: 'center', justifyContent: 'center' }}>
                      <MaterialIcons name="fact-check" size={36} color={colors.outline} />
                      <Text style={{ ...typography.bodyMd, color: colors.onSurfaceVariant, marginTop: 8 }}>
                        No recent inspections recorded.
                      </Text>
                      <Text style={{ ...typography.caption, color: colors.outline, marginTop: 4 }}>
                        Tap the + button below to start a new package inspection.
                      </Text>
                    </View>
                  ) : (
                    filteredInspections.map((item: any, idx: number) => {
                      const isLast = idx === filteredInspections.length - 1;
                      const badge = getStatusBadgeProps(item.overall_status || item.status);

                      return (
                        <TouchableOpacity
                          key={item.id || idx}
                          style={[styles.inspectionRow, !isLast && styles.rowBorder]}
                          onPress={() => {
                            navigation.navigate('Findings', {
                              inspectionId: item.id,
                              inspectionNumber: item.inspection_number,
                            });
                          }}
                          activeOpacity={0.7}
                        >
                          <Text style={styles.rowIdText}>{item.inspection_number}</Text>
                          <Text style={styles.rowProductText} numberOfLines={1}>
                            {item.product_name}
                          </Text>
                          <Text style={styles.rowLocationText} numberOfLines={1}>
                            {item.location}
                          </Text>
                          <View style={styles.badgeRow}>
                            <View
                              style={[
                                styles.statusBadge,
                                { backgroundColor: badge.bg, borderColor: badge.border },
                              ]}
                            >
                              <Text style={[styles.statusBadgeText, { color: badge.text }]}>
                                {badge.label}
                              </Text>
                            </View>
                          </View>
                        </TouchableOpacity>
                      );
                    })
                  )}
                </View>
              </View>
            </>
          )}
        </ScrollView>


        {/* Bottom Navigation Bar */}
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
    position: 'relative',
  },
  scrollContent: {
    paddingHorizontal: spacing.marginX,
    paddingTop: spacing.stackMd,
    // paddingBottom is calculated dynamically on the ScrollView via contentContainerStyle
    // to accommodate BottomNav height + safe-area bottom.
    // This static value is a fallback only.
    paddingBottom: 8,
  },
  welcomeHeader: {
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    paddingBottom: spacing.stackSm,
    marginBottom: spacing.stackSm,
  },
  welcomeHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  welcomeHeaderTextCol: {
    flex: 1,
    paddingRight: spacing.stackSm,
  },
  welcomeGreeting: {
    ...typography.headlineLg,
    fontSize: 20,
    lineHeight: 28,
    color: colors.primary,
  },
  welcomeSubtext: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.onSurfaceVariant,
    marginTop: spacing.tight,
  },
  metricsGrid: {
    gap: spacing.base,
    marginBottom: spacing.stackMd,
  },
  metricsRow: {
    flexDirection: 'row',
    gap: spacing.base,
  },
  metricCard: {
    flex: 1,
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.stackSm,
    flexDirection: 'column',
  },
  metricLabelDefault: {
    ...typography.labelCaps,
    fontSize: 12,
    lineHeight: 16,
    color: colors.onSurfaceVariant,
  },
  metricLabelAmber: {
    ...typography.labelCaps,
    fontSize: 12,
    lineHeight: 16,
    color: colors.statusAmberText,
  },
  metricLabelRed: {
    ...typography.labelCaps,
    fontSize: 12,
    lineHeight: 16,
    color: colors.statusRedText,
  },
  metricValuePrimary: {
    ...typography.headlineLg,
    fontSize: 20,
    lineHeight: 28,
    color: colors.primary,
    marginTop: spacing.tight,
  },
  metricValueAmber: {
    ...typography.headlineLg,
    fontSize: 20,
    lineHeight: 28,
    color: colors.statusAmberText,
    marginTop: spacing.tight,
  },
  metricValueRed: {
    ...typography.headlineLg,
    fontSize: 20,
    lineHeight: 28,
    color: colors.statusRedText,
    marginTop: spacing.tight,
  },
  chipsScroll: {
    marginBottom: spacing.stackMd,
  },
  chipsScrollContent: {
    gap: spacing.base,
    paddingBottom: 4,
  },
  chipButton: {
    paddingHorizontal: 16,
    paddingVertical: 6,
    borderRadius: borderRadius.round,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipText: {
    ...typography.labelCaps,
    fontSize: 12,
    lineHeight: 16,
  },
  recentSection: {
    gap: spacing.base,
  },
  sectionTitle: {
    ...typography.sectionHeader,
    fontSize: 16,
    lineHeight: 24,
    color: colors.primary,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    paddingBottom: spacing.tight,
  },
  recentCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    overflow: 'hidden',
  },
  inspectionRow: {
    padding: spacing.stackSm,
    gap: spacing.tight,
  },
  rowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  rowIdText: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.onSurfaceVariant,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  },
  rowProductText: {
    ...typography.bodyMd,
    fontSize: 14,
    lineHeight: 20,
    color: colors.onSurface,
  },
  rowLocationText: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.onSurfaceVariant,
  },
  badgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 2,
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    alignSelf: 'flex-start',
  },
  statusBadgeText: {
    ...typography.caption,
    fontSize: 12,
    lineHeight: 16,
  },
});
