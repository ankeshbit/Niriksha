import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { useNavigation, useRoute } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const BottomNav: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute();

  const currentRoute = route.name;

  const tabs: Array<{
    name: string;
    route: keyof RootStackParamList;
    icon: keyof typeof MaterialIcons.glyphMap;
    isPrimaryAction?: boolean;
  }> = [
    { name: 'Home', route: 'Dashboard', icon: 'home' },
    { name: 'Reports', route: 'ReportsList', icon: 'description' },
    { name: '+ NEW', route: 'NewInspection', icon: 'add-circle', isPrimaryAction: true },
    { name: 'Offline', route: 'DraftOffline', icon: 'cloud-off' },
    { name: 'Profile', route: 'Profile', icon: 'person' },
  ];

  return (
    <View style={styles.navContainer}>
      {tabs.map((tab) => {
        const isActive = currentRoute === tab.route;

        if (tab.isPrimaryAction) {
          return (
            <TouchableOpacity
              key={tab.name}
              onPress={() => navigation.navigate(tab.route as any)}
              style={styles.primaryActionButton}
              activeOpacity={0.8}
            >
              <MaterialIcons name="add" size={22} color={colors.onPrimary} />
              <Text style={styles.primaryActionText}>NEW</Text>
            </TouchableOpacity>
          );
        }

        return (
          <TouchableOpacity
            key={tab.name}
            onPress={() => navigation.navigate(tab.route as any)}
            style={styles.tabItem}
            activeOpacity={0.7}
          >
            <MaterialIcons
              name={tab.icon}
              size={22}
              color={isActive ? colors.primary : colors.secondary}
            />
            <Text
              style={[
                styles.tabLabel,
                { color: isActive ? colors.primary : colors.secondary, fontWeight: isActive ? '700' : '500' },
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
    backgroundColor: colors.surfaceContainerLowest,
    borderTopWidth: 1,
    borderTopColor: colors.borderSubtle,
    paddingVertical: 8,
    paddingHorizontal: spacing.gutter,
  },
  tabItem: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 4,
    minWidth: 50,
  },
  tabLabel: {
    ...typography.caption,
    fontSize: 11,
    marginTop: 2,
  },
  primaryActionButton: {
    backgroundColor: colors.primary,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: borderRadius.round,
    marginHorizontal: 4,
  },
  primaryActionText: {
    ...typography.caption,
    color: colors.onPrimary,
    fontWeight: '700',
    marginLeft: 2,
  },
});
