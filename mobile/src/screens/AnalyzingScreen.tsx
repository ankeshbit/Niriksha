import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ActivityIndicator, Alert } from 'react-native';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { MaterialIcons } from '@expo/vector-icons';
import { api } from '../services/api';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const AnalyzingScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'Analyzing'>>();
  const { inspectionId, inspectionNumber } = route.params;

  const [stepText, setStepText] = useState('Extracting optical text regions...');

  useEffect(() => {
    let isMounted = true;

    const executeAnalysis = async () => {
      try {
        if (isMounted) setStepText('Pre-processing image contrasts & CLAHE...');
        await new Promise((r) => setTimeout(r, 600));

        if (isMounted) setStepText('Parsing 7 mandatory PCR 2011 declarations...');
        await api.runOCR(inspectionId);

        if (isMounted) {
          navigation.replace('ExtractedDeclarations', {
            inspectionId,
            inspectionNumber,
          });
        }
      } catch (err: any) {
        Alert.alert('Analysis Error', err.message || 'Failed to complete OCR extraction.', [
          {
            text: 'Go Back',
            onPress: () => navigation.goBack(),
          },
        ]);
      }
    };

    executeAnalysis();

    return () => {
      isMounted = false;
    };
  }, [inspectionId]);

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        <View style={styles.iconCircle}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
        <Text style={styles.titleText}>ANALYZING PACKAGE</Text>
        <Text style={styles.subtitleText}>{stepText}</Text>
        <View style={styles.disclaimerBox}>
          <MaterialIcons name="memory" size={16} color={colors.onSurfaceVariant} />
          <Text style={styles.disclaimerText}>
            AI/OCR is restricted to text extraction. Statutory compliance rules will be deterministically checked.
          </Text>
        </View>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.gutter,
  },
  card: {
    width: '100%',
    maxWidth: 380,
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.stackLg,
    alignItems: 'center',
    gap: spacing.stackSm,
  },
  iconCircle: {
    marginBottom: spacing.stackSm,
  },
  titleText: {
    ...typography.headlineLg,
    color: colors.primary,
    textAlign: 'center',
  },
  subtitleText: {
    ...typography.bodySm,
    color: colors.onSurfaceVariant,
    textAlign: 'center',
  },
  disclaimerBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: 10,
    marginTop: spacing.stackSm,
    gap: 6,
  },
  disclaimerText: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
    flex: 1,
  },
});
