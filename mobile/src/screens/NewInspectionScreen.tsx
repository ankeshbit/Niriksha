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
  SafeAreaView,
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { BottomNav } from '../components/BottomNav';
import { ProfileAvatar } from '../components/ProfileAvatar';
import { api } from '../services/api';
import { authStorage } from '../services/authStorage';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const NewInspectionScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [profile, setProfile] = useState<any>(null);

  // Form Fields
  const [productName, setProductName] = useState('Premium Basmati Rice');
  const [brandName, setBrandName] = useState('Agro Foods');
  const [category, setCategory] = useState<'Packaged Food' | 'Household/Personal Care'>('Packaged Food');
  const [location, setLocation] = useState('Sector 4 Market');

  // Additional Details Accordion State & Fields
  const [additionalDetailsOpen, setAdditionalDetailsOpen] = useState(true);
  const [batchNumber, setBatchNumber] = useState('BN-2026-X1');
  const [manufacturer, setManufacturer] = useState('Agro Foods Pvt. Ltd.');
  const [source, setSource] = useState('Retail Distributor');
  const [inspectionContext, setInspectionContext] = useState<'Retail' | 'Warehouse' | 'E-commerce'>('Retail');
  const [notes, setNotes] = useState('Routine surveillance under Legal Metrology Rules, 2011');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    authStorage.getProfile().then((prof) => {
      if (prof) setProfile(prof);
    });
  }, []);

  const handleContinue = async () => {
    if (!productName.trim()) {
      Alert.alert('Required Field', 'Please enter the Product Name.');
      return;
    }
    if (!brandName.trim()) {
      Alert.alert('Required Field', 'Please enter the Brand.');
      return;
    }
    if (!location.trim()) {
      Alert.alert('Required Field', 'Please enter the Location.');
      return;
    }

    setLoading(true);

    try {
      const combinedNotes = [
        manufacturer ? `Manufacturer: ${manufacturer}` : '',
        source ? `Source: ${source}` : '',
        inspectionContext ? `Context: ${inspectionContext}` : '',
        notes ? `Notes: ${notes}` : '',
      ]
        .filter(Boolean)
        .join(' | ');

      const inspection = await api.createInspection({
        product_name: productName.trim(),
        brand_name: brandName.trim(),
        category,
        location: location.trim(),
        batch_number: batchNumber.trim() || undefined,
        notes: combinedNotes || undefined,
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

  const inspectorIdString = profile
    ? `${profile.full_name || 'Rajesh Kumar'} (${profile.officer_id || 'LM-IND-442'})`
    : 'Rajesh Kumar (LM-IND-442)';

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        {/* Stitch TopAppBar Header */}
        <View style={styles.topHeader}>
          <View style={styles.headerLeft}>
            <TouchableOpacity
              style={styles.backButton}
              onPress={() => navigation.navigate('Dashboard')}
              activeOpacity={0.7}
            >
              <MaterialIcons name="arrow-back" size={24} color={colors.primary} />
            </TouchableOpacity>
            <Text style={styles.headerTitle}>Step 1 of 3</Text>
          </View>
          <ProfileAvatar size={36} />
        </View>

        <ScrollView
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* Section 1: Inspection Details Card */}
          <View style={styles.cardSection}>
            <View style={styles.cardHeader}>
              <Text style={styles.cardHeaderText}>Inspection Details</Text>
            </View>

            <View style={styles.cardBody}>
              {/* Inspection ID (Readonly) */}
              <View style={styles.fieldGroup}>
                <Text style={styles.fieldLabel}>Inspection ID</Text>
                <TextInput
                  style={[styles.textInput, styles.readonlyInput]}
                  value="Auto-generated on save"
                  editable={false}
                />
              </View>

              {/* Date & Time (Readonly) */}
              <View style={styles.fieldGroup}>
                <Text style={styles.fieldLabel}>Date & Time</Text>
                <TextInput
                  style={[styles.textInput, styles.readonlyInput]}
                  value={currentDateStr}
                  editable={false}
                />
              </View>

              {/* Inspector ID (Readonly) */}
              <View style={styles.fieldGroup}>
                <Text style={styles.fieldLabel}>Inspector ID</Text>
                <TextInput
                  style={[styles.textInput, styles.readonlyInput]}
                  value={inspectorIdString}
                  editable={false}
                />
              </View>

              {/* Product Name * */}
              <View style={styles.fieldGroup}>
                <Text style={styles.fieldLabel}>
                  Product Name <Text style={{ color: colors.error }}>*</Text>
                </Text>
                <TextInput
                  style={styles.textInput}
                  value={productName}
                  onChangeText={setProductName}
                  placeholder="e.g. Premium Basmati Rice"
                  placeholderTextColor={colors.outline}
                />
              </View>

              {/* Brand * */}
              <View style={styles.fieldGroup}>
                <Text style={styles.fieldLabel}>
                  Brand <Text style={{ color: colors.error }}>*</Text>
                </Text>
                <TextInput
                  style={styles.textInput}
                  value={brandName}
                  onChangeText={setBrandName}
                  placeholder="e.g. Agro Foods"
                  placeholderTextColor={colors.outline}
                />
              </View>

              {/* Product Category * */}
              <View style={styles.fieldGroup}>
                <Text style={styles.fieldLabel}>
                  Product Category <Text style={{ color: colors.error }}>*</Text>
                </Text>
                <View style={styles.categoryToggleRow}>
                  <TouchableOpacity
                    style={[
                      styles.categoryToggleBtn,
                      category === 'Packaged Food' && styles.categoryToggleBtnActive,
                    ]}
                    onPress={() => setCategory('Packaged Food')}
                    activeOpacity={0.8}
                  >
                    <Text
                      style={[
                        styles.categoryToggleText,
                        category === 'Packaged Food' && styles.categoryToggleTextActive,
                      ]}
                    >
                      Packaged Food
                    </Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    style={[
                      styles.categoryToggleBtn,
                      category === 'Household/Personal Care' && styles.categoryToggleBtnActive,
                    ]}
                    onPress={() => setCategory('Household/Personal Care')}
                    activeOpacity={0.8}
                  >
                    <Text
                      style={[
                        styles.categoryToggleText,
                        category === 'Household/Personal Care' && styles.categoryToggleTextActive,
                      ]}
                    >
                      Household/Personal Care
                    </Text>
                  </TouchableOpacity>
                </View>
              </View>

              {/* Location */}
              <View style={styles.fieldGroup}>
                <Text style={styles.fieldLabel}>Location</Text>
                <TextInput
                  style={styles.textInput}
                  value={location}
                  onChangeText={setLocation}
                  placeholder="e.g. Sector 4 Market"
                  placeholderTextColor={colors.outline}
                />
              </View>
            </View>
          </View>

          {/* Section 2: Additional Details Accordion Card */}
          <View style={styles.cardSection}>
            <TouchableOpacity
              style={styles.accordionHeader}
              onPress={() => setAdditionalDetailsOpen(!additionalDetailsOpen)}
              activeOpacity={0.8}
            >
              <Text style={styles.cardHeaderText}>Additional Details</Text>
              <MaterialIcons
                name={additionalDetailsOpen ? 'expand-less' : 'expand-more'}
                size={22}
                color={colors.primary}
              />
            </TouchableOpacity>

            {additionalDetailsOpen && (
              <View style={styles.cardBody}>
                {/* Batch Number */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.fieldLabel}>Batch Number</Text>
                  <TextInput
                    style={styles.textInput}
                    value={batchNumber}
                    onChangeText={setBatchNumber}
                    placeholder="Enter batch number"
                    placeholderTextColor={colors.outline}
                  />
                </View>

                {/* Manufacturer */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.fieldLabel}>Manufacturer</Text>
                  <TextInput
                    style={styles.textInput}
                    value={manufacturer}
                    onChangeText={setManufacturer}
                    placeholder="Enter manufacturer"
                    placeholderTextColor={colors.outline}
                  />
                </View>

                {/* Source */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.fieldLabel}>Source</Text>
                  <TextInput
                    style={styles.textInput}
                    value={source}
                    onChangeText={setSource}
                    placeholder="Enter source"
                    placeholderTextColor={colors.outline}
                  />
                </View>

                {/* Inspection Context */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.fieldLabel}>Inspection Context</Text>
                  <View style={styles.categoryToggleRow}>
                    {(['Retail', 'Warehouse', 'E-commerce'] as const).map((ctx) => (
                      <TouchableOpacity
                        key={ctx}
                        style={[
                          styles.contextBtn,
                          inspectionContext === ctx && styles.categoryToggleBtnActive,
                        ]}
                        onPress={() => setInspectionContext(ctx)}
                        activeOpacity={0.8}
                      >
                        <Text
                          style={[
                            styles.categoryToggleText,
                            inspectionContext === ctx && styles.categoryToggleTextActive,
                          ]}
                        >
                          {ctx}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>

                {/* Notes */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.fieldLabel}>Notes</Text>
                  <TextInput
                    style={[styles.textInput, styles.textArea]}
                    value={notes}
                    onChangeText={setNotes}
                    placeholder="Enter any additional notes"
                    placeholderTextColor={colors.outline}
                    multiline
                    numberOfLines={3}
                  />
                </View>
              </View>
            )}
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
              <View style={styles.continueBtnContent}>
                <Text style={styles.continueBtnText}>Continue</Text>
                <MaterialIcons name="arrow-forward" size={18} color={colors.onPrimary} />
              </View>
            )}
          </TouchableOpacity>
        </ScrollView>

        {/* Bottom Navigation */}
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
  },
  topHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.surfaceContainerLowest,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    height: 56,
    paddingHorizontal: spacing.gutter,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  backButton: {
    padding: 6,
    borderRadius: borderRadius.round,
  },
  headerTitle: {
    ...typography.headlineLg,
    fontSize: 20,
    lineHeight: 28,
    fontWeight: '700',
    color: colors.primary,
  },
  avatarCircle: {
    width: 32,
    height: 32,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    backgroundColor: colors.surfaceContainerLow,
    alignItems: 'center',
    justifyContent: 'center',
  },
  scrollContent: {
    paddingHorizontal: spacing.gutter,
    paddingTop: spacing.stackMd,
    paddingBottom: 90,
    gap: spacing.stackMd,
  },
  cardSection: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    overflow: 'hidden',
  },
  cardHeader: {
    paddingHorizontal: spacing.gutter,
    paddingVertical: spacing.base,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  accordionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.gutter,
    paddingVertical: spacing.base,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  cardHeaderText: {
    ...typography.sectionHeader,
    fontSize: 16,
    lineHeight: 24,
    fontWeight: '600',
    color: colors.primary,
  },
  cardBody: {
    padding: spacing.gutter,
    gap: 16,
  },
  fieldGroup: {
    gap: 8,
  },
  fieldLabel: {
    ...typography.labelCaps,
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 0.24,
    color: colors.onSurfaceVariant,
  },
  textInput: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.base,
    ...typography.bodyMd,
    fontSize: 14,
    lineHeight: 20,
    color: colors.onSurface,
  },
  readonlyInput: {
    backgroundColor: colors.surfaceContainerLow,
    color: colors.onSurfaceVariant,
  },
  textArea: {
    minHeight: 70,
    textAlignVertical: 'top',
  },
  categoryToggleRow: {
    flexDirection: 'row',
    gap: 8,
  },
  categoryToggleBtn: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    paddingHorizontal: 8,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    backgroundColor: colors.surfaceContainerLowest,
  },
  contextBtn: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    paddingHorizontal: 6,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    backgroundColor: colors.surfaceContainerLowest,
  },
  categoryToggleBtnActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  categoryToggleText: {
    ...typography.bodySm,
    fontSize: 13,
    fontWeight: '500',
    color: colors.onSurface,
    textAlign: 'center',
  },
  categoryToggleTextActive: {
    color: colors.onPrimary,
    fontWeight: '700',
  },
  continueButton: {
    backgroundColor: colors.primaryContainer,
    paddingVertical: 12,
    paddingHorizontal: spacing.gutter,
    borderRadius: borderRadius.lg,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 8,
    marginBottom: 16,
  },
  continueBtnContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  continueBtnText: {
    ...typography.labelCaps,
    fontSize: 14,
    lineHeight: 18,
    fontWeight: '600',
    color: colors.onPrimary,
  },
});
