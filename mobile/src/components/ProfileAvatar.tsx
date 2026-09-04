import React from 'react';
import { View, StyleSheet, StyleProp, ViewStyle } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { colors } from '../theme/tokens';

export interface ProfileAvatarProps {
  /** Diameter of the circular avatar in pixels (default: 36) */
  size?: number;
  /** Size of the user silhouette icon (default: size * 0.58) */
  iconSize?: number;
  /** Custom container styling */
  style?: StyleProp<ViewStyle>;
  /** Silhouette icon color (default: neutral slate/gray) */
  iconColor?: string;
  /** Circular background color (default: neutral light gray) */
  backgroundColor?: string;
  /** Border color (default: subtle outline) */
  borderColor?: string;
  /** Border width (default: 1) */
  borderWidth?: number;
}

/**
 * Consistent, neutral "no profile photo" avatar placeholder component.
 * Renders a circular area with a neutral light-gray background and a simple gray user silhouette.
 */
export const ProfileAvatar: React.FC<ProfileAvatarProps> = ({
  size = 36,
  iconSize,
  style,
  iconColor = colors.secondary,
  backgroundColor = colors.surfaceContainerHighest,
  borderColor = colors.borderSubtle,
  borderWidth = 1,
}) => {
  const calculatedIconSize = iconSize ?? Math.round(size * 0.58);

  return (
    <View
      style={[
        styles.avatarCircle,
        {
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor,
          borderColor,
          borderWidth,
        },
        style,
      ]}
      accessibilityRole="image"
      accessibilityLabel="Profile avatar placeholder"
    >
      <MaterialIcons name="person" size={calculatedIconSize} color={iconColor} />
    </View>
  );
};

const styles = StyleSheet.create({
  avatarCircle: {
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
});
