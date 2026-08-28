import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, StatusBar } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

interface AppHeaderProps {
  title?: string;
  subtitle?: string;
  showBack?: boolean;
  onBackPress?: () => void;
  rightAction?: {
    icon: keyof typeof MaterialIcons.glyphMap;
    label?: string;
    onPress: () => void;
  };
  variant?: 'primary' | 'surface';
}

export const AppHeader: React.FC<AppHeaderProps> = ({
  title = 'LEGAL METROLOGY',
  subtitle,
  showBack = false,
  onBackPress,
  rightAction,
  variant = 'primary',
}) => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();

  const isPrimary = variant === 'primary';
  const bgColor = isPrimary ? colors.primary : colors.surfaceContainerLowest;
  const textColor = isPrimary ? colors.onPrimary : colors.primary;
  const subtextColor = isPrimary ? colors.onPrimaryContainer : colors.onSurfaceVariant;
  const iconColor = isPrimary ? colors.onPrimary : colors.primary;

  const handleBack = () => {
    if (onBackPress) {
      onBackPress();
    } else if (navigation.canGoBack()) {
      navigation.goBack();
    } else {
      navigation.navigate('Dashboard');
    }
  };

  return (
    <View style={[styles.headerContainer, { backgroundColor: bgColor }]}>
      <StatusBar barStyle={isPrimary ? 'light-content' : 'dark-content'} backgroundColor={bgColor} />
      <View style={styles.contentRow}>
        <View style={styles.leftContainer}>
          {showBack && (
            <TouchableOpacity onPress={handleBack} style={styles.iconButton} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
              <MaterialIcons name="arrow-back" size={24} color={iconColor} />
            </TouchableOpacity>
          )}
          <View style={styles.titleContainer}>
            <Text style={[typography.headlineLg, { color: textColor, fontSize: 17, lineHeight: 22 }]} numberOfLines={1}>
              {title}
            </Text>
            {subtitle ? (
              <Text style={[typography.caption, { color: subtextColor }]} numberOfLines={1}>
                {subtitle}
              </Text>
            ) : null}
          </View>
        </View>

        {rightAction && (
          <TouchableOpacity
            onPress={rightAction.onPress}
            style={[styles.rightButton, isPrimary ? styles.rightButtonPrimary : styles.rightButtonSurface]}
          >
            {rightAction.label ? (
              <Text style={[styles.rightButtonText, { color: isPrimary ? colors.onPrimary : colors.primary }]}>
                {rightAction.label}
              </Text>
            ) : null}
            <MaterialIcons name={rightAction.icon} size={20} color={iconColor} />
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  headerContainer: {
    paddingTop: 8,
    paddingBottom: 12,
    paddingHorizontal: spacing.gutter,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  contentRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  leftContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  iconButton: {
    marginRight: 10,
    padding: 4,
  },
  titleContainer: {
    flex: 1,
  },
  rightButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: borderRadius.lg,
  },
  rightButtonPrimary: {
    backgroundColor: colors.primaryContainer,
  },
  rightButtonSurface: {
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  rightButtonText: {
    ...typography.caption,
    fontWeight: '600',
    marginRight: 4,
  },
});
