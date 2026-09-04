import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { MaterialIcons } from '@expo/vector-icons';

interface MetricCardProps {
  title: string;
  count: number | string;
  icon: keyof typeof MaterialIcons.glyphMap;
  color?: string;
  bgColor?: string;
  onPress?: () => void;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  count,
  icon,
  color = colors.primary,
  bgColor = colors.surfaceContainerLow,
  onPress,
}) => {
  const formattedCount = typeof count === 'number' ? String(count).padStart(2, '0') : count;

  return (
    <TouchableOpacity
      style={[styles.cardContainer, { backgroundColor: bgColor }]}
      onPress={onPress}
      disabled={!onPress}
      activeOpacity={0.7}
    >
      <View style={styles.topRow}>
        <Text style={[typography.labelCaps, { color: colors.onSurfaceVariant, fontSize: 11 }]}>
          {title}
        </Text>
        <MaterialIcons name={icon} size={18} color={color} />
      </View>
      <Text style={[typography.headlineLg, { color, fontSize: 24, lineHeight: 30, marginTop: 4 }]}>
        {formattedCount}
      </Text>
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  cardContainer: {
    flex: 1,
    padding: spacing.stackMd,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    minHeight: 80,
    justifyContent: 'space-between',
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
});
