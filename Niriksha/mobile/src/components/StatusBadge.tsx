import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, typography, borderRadius } from '../theme/tokens';

export type InspectionStatusType =
  | 'VERIFIED_COMPLIANT'
  | 'NO_POTENTIAL_VIOLATIONS'
  | 'POTENTIAL_NON_COMPLIANCE'
  | 'NEEDS_MANUAL_VERIFICATION'
  | 'INSUFFICIENT_EVIDENCE'
  | 'DRAFT'
  | 'COMPLETED'
  | string;

interface StatusBadgeProps {
  status?: InspectionStatusType;
  label?: string;
  size?: 'sm' | 'md';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label, size = 'sm' }) => {
  let bgColor = colors.surfaceContainerLow;
  let textColor = colors.secondary;
  let borderColor = colors.borderSubtle;
  let text = label || 'DRAFT';

  if (status === 'VERIFIED_COMPLIANT' || status === 'NO_POTENTIAL_VIOLATIONS' || status === 'PASS') {
    bgColor = colors.statusGreenBg;
    textColor = colors.statusGreenText;
    borderColor = colors.statusGreenText;
    text = label || 'Verified Compliant';
  } else if (status === 'POTENTIAL_NON_COMPLIANCE' || status === 'FAIL' || status === 'CONFIRMED') {
    bgColor = colors.statusRedBg;
    textColor = colors.statusRedText;
    borderColor = colors.statusRedText;
    text = label || 'Potential Non-Compliance';
  } else if (status === 'NEEDS_MANUAL_VERIFICATION' || status === 'INSUFFICIENT_EVIDENCE' || status === 'WARNING') {
    bgColor = colors.statusAmberBg;
    textColor = colors.statusAmberText;
    borderColor = colors.statusAmberText;
    text = label || 'Needs Verification';
  } else if (status === 'DISMISSED') {
    bgColor = colors.statusGreenBg;
    textColor = colors.statusGreenText;
    borderColor = colors.statusGreenText;
    text = label || 'Dismissed';
  }

  return (
    <View
      style={[
        styles.badgeContainer,
        { backgroundColor: bgColor, borderColor },
        size === 'md' ? styles.badgeMd : styles.badgeSm,
      ]}
    >
      <Text style={[styles.badgeText, { color: textColor, fontSize: size === 'md' ? 12 : 11 }]}>
        {text}
      </Text>
    </View>
  );
};

const styles = StyleSheet.create({
  badgeContainer: {
    borderWidth: 1,
    borderRadius: borderRadius.sm,
    alignSelf: 'flex-start',
    justifyContent: 'center',
    alignItems: 'center',
  },
  badgeSm: {
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  badgeMd: {
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  badgeText: {
    ...typography.caption,
    fontWeight: '600',
  },
});
