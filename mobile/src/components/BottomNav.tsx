import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { useNavigation, useRoute } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';
import { authStorage } from '../services/authStorage';

/**
 * The visible height of the tab bar row (icons + labels + vertical padding).
 * Does NOT include the bottom safe-area inset — that is added dynamically.
 */
export const BOTTOM_NAV_TAB_HEIGHT = 56;

export const BottomNav: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute();
  const insets = useSafeAreaInsets();
  const [role, setRole] = useState<string>('INSPECTOR');

  const currentRoute = route.name;

  useEffect(() => {
    let mounted = true;
    authStorage.getProfile().then((profile) => {
      if (mounted && profile && profile.role) {
        setRole(profile.role.toUpperCase());
      }
    }).catch(() => {});
    return () => {
      mounted = false;
    };
  }, []);

  const isSupervisor = role === 'SUPERVISOR';

  const tabs: Array<{
    name: string;
    route: keyof RootStackParamList;
    icon: keyof typeof MaterialIcons.glyphMap;
  }> = isSupervisor
    ? [
        { name: 'Dashboard', route: 'SupervisorDashboard', icon: 'dashboard' },
        { name: 'Inspections', route: 'SupervisorAllInspections', icon: 'view-list' },
        { name: 'Inspectors', route: 'SupervisorInspectors', icon: 'groups' },
        { name: 'Reports', route: 'ReportsList', icon: 'assessment' },
        { name: 'Profile', route: 'Profile', icon: 'person' },
      ]
    : [
        { name: 'Home', route: 'Dashboard', icon: 'home' },
        { name: 'Inspections', route: 'Inspections', icon: 'fact-check' },
        { name: 'New', route: 'NewInspection', icon: 'add-circle' },
        { name: 'Reports', route: 'ReportsList', icon: 'assessment' },
        { name: 'Profile', route: 'Profile', icon: 'person' },
      ];

  return (
    <View style={[styles.navContainer, { paddingBottom: Math.max(insets.bottom, 6) }]}>
      {tabs.map((tab) => {
        const isActive =
          (tab.route === 'SupervisorDashboard' && currentRoute === 'SupervisorDashboard') ||
          (tab.route === 'SupervisorAllInspections' &&
            (currentRoute === 'SupervisorAllInspections' || currentRoute === 'SupervisorInspectionDetail')) ||
          (tab.route === 'SupervisorInspectors' && currentRoute === 'SupervisorInspectors') ||
          (tab.route === 'Dashboard' && currentRoute === 'Dashboard') ||
          (tab.route === 'Inspections' &&
            (currentRoute === 'Inspections' || currentRoute === 'DraftOffline')) ||
          (tab.route === 'NewInspection' && currentRoute === 'NewInspection') ||
          (tab.route === 'ReportsList' && currentRoute === 'ReportsList') ||
          (tab.route === 'Profile' && currentRoute === 'Profile');

        return (
          <TouchableOpacity
            key={tab.name}
            testID={`bottom-nav-${tab.name.toLowerCase()}`}
            accessibilityRole="button"
            accessibilityLabel={`BottomNav-${tab.name}`}
            onPress={() => {
              // Do not push a duplicate screen if we are already on this route
              if (currentRoute !== tab.route) {
                navigation.navigate(tab.route as any);
              }
            }}
            style={[styles.tabItem, isActive && styles.activeTabItem]}
            activeOpacity={0.7}
          >
            <MaterialIcons
              name={tab.icon}
              size={22}
              color={isActive ? colors.primary : colors.onSurfaceVariant}
            />
            <Text
              style={[
                styles.tabLabel,
                {
                  color: isActive ? colors.primary : colors.onSurfaceVariant,
                  fontWeight: isActive ? '600' : '400',
                },
              ]}
            >
              {tab.name}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
};

const styles = StyleSheet.create({
  navContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.borderSubtle,
    paddingTop: 6,
    paddingHorizontal: spacing.tight,
    // paddingBottom is set dynamically in JSX above via insets.bottom
  },
  tabItem: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 4,
    paddingHorizontal: 12,
    borderRadius: borderRadius.xl,
    minWidth: 60,
  },
  activeTabItem: {
    backgroundColor: colors.secondaryContainer,
  },
  tabLabel: {
    ...typography.caption,
    fontSize: 12,
    lineHeight: 16,
    marginTop: 2,
  },
});
