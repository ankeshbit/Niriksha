import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { AppHeader } from '../components/AppHeader';
import { api } from '../services/api';
import { authStorage } from '../services/authStorage';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const NewInspectionScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [profile, setProfile] = useState<any>(null);

  const [productName, setProductName] = useState('Fortune Sunlite Refined Sunflower Oil 1L');
  const [brandName, setBrandName] = useState('Fortune');
  const [category, setCategory] = useState<'Packaged Food' | 'Household/Personal Care'>('Packaged Food');
  const [location, setLocation] = useState('Azadpur Wholesale Mandi Delhi');
  const [batchNumber, setBatchNumber] = useState('SUN-2026-B1');
  const [notes, setNotes] = useState('Routine retail market surveillance under PCR 2011');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    authStorage.getProfile().then((prof) => {
      if (prof) setProfile(prof);
    });
  }, []);

  const handleContinue = async () => {
    if (!productName.trim()) {
      Alert.alert('Required Field', 'Please enter the packaged commodity name.');
      return;
    }
    if (!location.trim()) {
      Alert.alert('Required Field', 'Please enter the inspection location/site.');
      return;
    }

    setLoading(true);

    try {
      const inspection = await api.createInspection({
        product_name: productName.trim(),
        brand_name: brandName.trim() || undefined,
        category,
        location: location.trim(),
        batch_number: batchNumber.trim() || undefined,
        notes: notes.trim() || undefined,
      });

      navigation.navigate('CaptureImages', {
        inspectionId: inspection.id,
        inspectionNumber: inspection.inspection_number,
      });
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to create inspection record.');
    } finally {
      setLoading(false);
    }
  };

  const currentDateStr = new Date().toLocaleString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={styles.container}
    >
      <AppHeader
        title="NEW INSPECTION"
        subtitle="Step 1 of 3: Commodity Information"
        showBack={true}
        onBackPress={() => navigation.navigate('Dashboard')}
      />

      <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
        <View style={styles.formCard}>
          {/* Readonly Metadata Section */}
          <View style={styles.metaRow}>
            <View style={styles.metaCol}>
              <Text style={styles.metaLabel}>INSPECTION NUMBER</Text>
              <Text style={styles.metaValue}>Auto-generated on Save</Text>
            </View>
            <View style={styles.metaCol}>
              <Text style={styles.metaLabel}>DATE & TIME</Text>
              <Text style={styles.metaValue}>{currentDateStr}</Text>
            </View>
          </View>

          <View style={styles.divider} />

          <View style={styles.metaRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.metaLabel}>INSPECTING OFFICER</Text>
              <Text style={styles.metaValueBold}>
                {profile?.full_name || 'Inspector'} ({profile?.officer_id || 'DOCA-INSP-842'})
              </Text>
            </View>
          </View>

          <View style={styles.divider} />

          {/* Form Fields */}
          <View style={styles.inputGroup}>
            <Text style={styles.fieldLabel}>
              Packaged Commodity Name <Text style={{ color: colors.statusRedText }}>*</Text>
            </Text>
            <TextInput
              style={styles.textInput}
              value={productName}
              onChangeText={setProductName}
              placeholder="e.g. Premium Basmati Rice 5kg"
              placeholderTextColor={colors.outline}
            />
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.fieldLabel}>Brand / Trademark</Text>
            <TextInput
              style={styles.textInput}
              value={brandName}
              onChangeText={setBrandName}
              placeholder="e.g. Agro Gold"
              placeholderTextColor={colors.outline}
            />
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.fieldLabel}>Commodity Category</Text>
            <View style={styles.categoryToggleRow}>
              <TouchableOpacity
                style={[
                  styles.categoryButton,
                  category === 'Packaged Food' && styles.categoryButtonActive,
                ]}
                onPress={() => setCategory('Packaged Food')}
                activeOpacity={0.8}
              >
                <MaterialIcons
                  name="restaurant"
                  size={16}
                  color={category === 'Packaged Food' ? colors.onPrimary : colors.onSurface}
                />
                <Text
                  style={[
                    styles.categoryText,
                    category === 'Packaged Food' && styles.categoryTextActive,
                  ]}
                >
                  Packaged Food
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[
                  styles.categoryButton,
                  category === 'Household/Personal Care' && styles.categoryButtonActive,
                ]}
                onPress={() => setCategory('Household/Personal Care')}
                activeOpacity={0.8}
              >
                <MaterialIcons
                  name="clean-hands"
                  size={16}
                  color={category === 'Household/Personal Care' ? colors.onPrimary : colors.onSurface}
                />
                <Text
                  style={[
                    styles.categoryText,
                    category === 'Household/Personal Care' && styles.categoryTextActive,
                  ]}
                >
                  Household / Care
                </Text>
              </TouchableOpacity>
            </View>
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.fieldLabel}>
              Inspection Site / Location <Text style={{ color: colors.statusRedText }}>*</Text>
            </Text>
            <TextInput
              style={styles.textInput}
              value={location}
              onChangeText={setLocation}
              placeholder="e.g. Azadpur Mandi Delhi"
              placeholderTextColor={colors.outline}
            />
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.fieldLabel}>Batch / Lot Number</Text>
            <TextInput
              style={styles.textInput}
              value={batchNumber}
              onChangeText={setBatchNumber}
              placeholder="e.g. BN-2026-X1"
              placeholderTextColor={colors.outline}
            />
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.fieldLabel}>Field Notes / Observations</Text>
            <TextInput
              style={[styles.textInput, styles.textArea]}
              value={notes}
              onChangeText={setNotes}
              placeholder="Additional field notes..."
              placeholderTextColor={colors.outline}
              multiline
              numberOfLines={3}
            />
          </View>

          {/* Continue Button */}
          <TouchableOpacity
            style={styles.continueButton}
            onPress={handleContinue}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading ? (
              <ActivityIndicator size="small" color={colors.onPrimary} />
            ) : (
              <View style={styles.buttonInner}>
                <Text style={styles.continueButtonText}>Continue to Image Capture</Text>
                <MaterialIcons name="arrow-forward" size={18} color={colors.onPrimary} />
              </View>
            )}
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.surface,
  },
  scrollContent: {
    padding: spacing.gutter,
    paddingBottom: 32,
  },
  formCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.marginX,
    gap: spacing.stackMd,
  },
  metaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  metaCol: {
    flex: 1,
  },
  metaLabel: {
    ...typography.labelCaps,
    fontSize: 10,
    color: colors.onSurfaceVariant,
  },
  metaValue: {
    ...typography.bodySm,
    color: colors.onSurface,
    marginTop: 2,
  },
  metaValueBold: {
    ...typography.bodyMdMedium,
    color: colors.primary,
    marginTop: 2,
  },
  divider: {
    height: 1,
    backgroundColor: colors.surfaceContainerHigh,
  },
  inputGroup: {
    gap: 4,
  },
  fieldLabel: {
    ...typography.labelCaps,
    color: colors.onSurfaceVariant,
  },
  textInput: {
    backgroundColor: colors.surfaceBright,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    paddingHorizontal: 12,
    paddingVertical: 8,
    ...typography.bodyMd,
    color: colors.onSurface,
  },
  textArea: {
    minHeight: 64,
    textAlignVertical: 'top',
  },
  categoryToggleRow: {
    flexDirection: 'row',
    gap: 8,
  },
  categoryButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    paddingHorizontal: 10,
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    gap: 6,
  },
  categoryButtonActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  categoryText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.onSurface,
  },
  categoryTextActive: {
    color: colors.onPrimary,
  },
  continueButton: {
    backgroundColor: colors.primary,
    paddingVertical: 12,
    borderRadius: borderRadius.lg,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.stackSm,
  },
  buttonInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  continueButtonText: {
    ...typography.sectionHeader,
    color: colors.onPrimary,
  },
});
