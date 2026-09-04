import React, { useState, useEffect, useCallback, useRef } from 'react';
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
import { SafeAreaView } from 'react-native-safe-area-context';
import { MaterialIcons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { BottomNav } from '../components/BottomNav';
import { ProfileAvatar } from '../components/ProfileAvatar';
import { api } from '../services/api';
import { authStorage } from '../services/authStorage';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

import { draftStorage } from '../services/draftStorage';
import { networkService } from '../services/networkService';

export const NewInspectionScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [profile, setProfile] = useState<any>(null);

  // Form Fields — intentionally empty so the user must fill them before Continue fires
  const [productName, setProductName] = useState('');
  const [brandName, setBrandName] = useState('');
  const [category, setCategory] = useState<'Packaged Food' | 'Household/Personal Care'>('Packaged Food');
  const [location, setLocation] = useState('');

  // Location detection state
  const [locationLoading, setLocationLoading] = useState(false);
  const [locationStatus, setLocationStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const locationLoadingRef = useRef(false);

  // Additional Details Accordion State & Fields
  const [additionalDetailsOpen, setAdditionalDetailsOpen] = useState(false);
  const [batchNumber, setBatchNumber] = useState('');
  const [manufacturer, setManufacturer] = useState('');
  const [source, setSource] = useState('');
  const [inspectionContext, setInspectionContext] = useState<'Retail' | 'Warehouse' | 'E-commerce'>('Retail');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  // Ref-based in-flight guard: prevents a second POST even if the user manages
  // to press Continue again before the first setLoading(true) re-render fires.
  const submittingRef = useRef(false);
  // Client draft ID for idempotent backend creation & offline consistency
  const clientDraftIdRef = useRef(draftStorage.generateClientDraftId());

  useEffect(() => {
    authStorage.getProfile().then((prof) => {
      if (prof) setProfile(prof);
    });
  }, []);

  // Track whether the next focus event should reset the form.
  // Resets ONLY when arriving afresh from another screen (e.g., navigating from Dashboard or after an inspection).
  // Does NOT reset when re-focusing due to system permission dialog, alert dismissal,
  // browser window focus, or while location detection is active.
  const shouldResetOnNextFocusRef = useRef(true);

  useEffect(() => {
    const unsubscribeBlur = navigation.addListener('blur', () => {
      shouldResetOnNextFocusRef.current = true;
    });
    return unsubscribeBlur;
  }, [navigation]);

  useFocusEffect(
    useCallback(() => {
      if (shouldResetOnNextFocusRef.current && !locationLoadingRef.current) {
        shouldResetOnNextFocusRef.current = false;
        setProductName('');
        setBrandName('');
        setCategory('Packaged Food');
        setLocation('');
        setLocationLoading(false);
        setLocationStatus('idle');
        locationLoadingRef.current = false;
        setAdditionalDetailsOpen(false);
        setBatchNumber('');
        setManufacturer('');
        setSource('');
        setInspectionContext('Retail');
        setNotes('');
        setLoading(false);
        clientDraftIdRef.current = draftStorage.generateClientDraftId();
      }
    }, [])
  );

  /**
   * Helper to run a promise with a timeout so GPS/network operations never hang indefinitely.
   */
  const withTimeout = <T,>(promise: Promise<T>, ms: number, timeoutMsg: string): Promise<T> => {
    return Promise.race([
      promise,
      new Promise<T>((_, reject) => setTimeout(() => reject(new Error(timeoutMsg)), ms)),
    ]);
  };

  /**
   * Formats a reverse-geocoded place into a clean, human-readable address.
   * Handles Indian postal structures as well as standard global formats.
   * Always returns a readable address (e.g. "Azadpur, Delhi, India" or "Sector/Street, City, Region, Country")
   * and never raw latitude/longitude coordinates.
   */
  const formatGeocodedAddress = (place: Location.LocationGeocodedAddress): string => {
    // If a full formattedAddress is already provided by the OS geocoder, verify it's not raw coords
    if (place.formattedAddress && typeof place.formattedAddress === 'string' && place.formattedAddress.trim()) {
      let cleaned = place.formattedAddress.trim();
      // Strip leading plus-codes if present (e.g., "7JWV+XX Azadpur, Delhi")
      cleaned = cleaned.replace(/^[A-Z0-9]{4,8}\+[A-Z0-9]{2,}\s*,?\s*/i, '').trim();
      const isRawCoord =
        /^[-+]?([1-8]?\d(\.\d+)?|90(\.0+)?),\s*[-+]?(180(\.0+)?|((1[0-7]\d)|([1-9]?\d))(\.\d+)?)$/.test(cleaned) ||
        /^[0-9+.,\s-]+(N|S|E|W)?$/i.test(cleaned);
      if (cleaned && !isRawCoord && /[a-zA-Z]/.test(cleaned)) {
        return cleaned;
      }
    }

    const candidateParts: string[] = [];

    const addPart = (part: string | null | undefined) => {
      if (!part || typeof part !== 'string') return;
      const trimmed = part.trim();
      if (!trimmed) return;
      // Skip unwanted placeholder values
      const lower = trimmed.toLowerCase();
      if (['null', 'undefined', 'unnamed road', 'unknown location', 'unnamed'].includes(lower)) return;
      // Skip pure coordinates or plus-codes
      const isCodeOrCoord =
        /^[0-9+.,\s-]+(N|S|E|W)?$/i.test(trimmed) ||
        /^[A-Z0-9]{4,8}\+[A-Z0-9]{2,}/.test(trimmed) ||
        /^[-+]?([1-8]?\d(\.\d+)?|90(\.0+)?),\s*[-+]?(180(\.0+)?|((1[0-7]\d)|([1-9]?\d))(\.\d+)?)$/.test(trimmed);
      if (isCodeOrCoord) return;
      // Case-insensitive deduplication
      if (!candidateParts.some((p) => p.toLowerCase() === lower)) {
        candidateParts.push(trimmed);
      }
    };

    // 1. Place / Building / Market Name
    addPart(place.name);

    // 2. Street number + Street (e.g., "12 Main Road" or "Sector 4")
    const streetComponents = [place.streetNumber, place.street]
      .filter((s): s is string => typeof s === 'string' && s.trim().length > 0)
      .map((s) => s.trim());
    const combinedStreet = streetComponents.join(' ').trim();
    if (combinedStreet) {
      addPart(combinedStreet);
    }

    // 3. District / Subregion (e.g., "Azadpur", "North West Delhi")
    addPart(place.district);
    addPart(place.subregion);

    // 4. City (e.g., "New Delhi")
    addPart(place.city);

    // 5. Region / State (e.g., "Delhi", "Jharkhand")
    addPart(place.region);

    // 6. Postal Code (e.g., "110033", "834001") - only if we already have other place details
    if (candidateParts.length > 0 && place.postalCode && typeof place.postalCode === 'string' && place.postalCode.trim()) {
      addPart(place.postalCode);
    }

    // 7. Country (e.g., "India")
    addPart(place.country);

    return candidateParts.join(', ').trim();
  };

  /**
   * Detects current GPS location and reverse-geocodes it into the Location field.
   * Only runs when the inspector explicitly taps "Use Current Location".
   * Never blocks manual entry. Handles all failure modes gracefully.
   * Platform-aware:
   *   - Native (Android/iOS): full GPS + reverseGeocodeAsync + human-readable address formatting.
   *   - Web: browser geolocation only; does NOT call reverseGeocodeAsync() (removed in SDK 49).
   */
  const handleUseCurrentLocation = async () => {
    // Prevent multiple simultaneous requests
    if (locationLoadingRef.current) return;
    locationLoadingRef.current = true;
    setLocationLoading(true);
    setLocationStatus('idle');

    console.log(`[Location] Platform: ${Platform.OS}`);

    // --- WEB IMPLEMENTATION ---
    if (Platform.OS === 'web') {
      try {
        console.log('[Location] Web platform detected, requesting browser geolocation...');
        const coords = await new Promise<{ latitude: number; longitude: number }>((resolve, reject) => {
          if (typeof navigator !== 'undefined' && navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
              (pos) => resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
              (err) => reject(err),
              { timeout: 10000, enableHighAccuracy: true }
            );
          } else {
            reject(new Error('Browser geolocation is not supported in this environment'));
          }
        });

        console.log(`[Location] Coordinates: lat=${coords.latitude}, lon=${coords.longitude}`);
        console.log('[Location] Reverse geocoding: skipped on Web (Geocoding API removed in SDK 49)');
        console.log('[Location] Final address: (manual entry requested)');
        setLocationStatus('idle');
        Alert.alert(
          'Location Detected',
          'Current location detected. Please enter the location manually.',
          [{ text: 'OK' }]
        );
      } catch (webErr: any) {
        console.warn('[Location] Web geolocation failed:', webErr);
        setLocationStatus('error');
        Alert.alert(
          'Location Detection Failed',
          'Unable to detect browser location. Please enter the location manually.',
          [{ text: 'OK' }]
        );
      } finally {
        locationLoadingRef.current = false;
        setLocationLoading(false);
      }
      return;
    }

    // --- NATIVE (ANDROID / iOS) IMPLEMENTATION ---
    try {
      // 1. Check if device location services (GPS) are enabled
      console.log('[Location] Checking location services enabled...');
      let servicesEnabled = true;
      try {
        servicesEnabled = await Location.hasServicesEnabledAsync();
      } catch (svcErr) {
        console.warn('[Location] hasServicesEnabledAsync threw, proceeding to permission check:', svcErr);
      }
      console.log(`[Location] Services enabled: ${servicesEnabled}`);

      if (!servicesEnabled) {
        setLocationStatus('error');
        Alert.alert(
          'Location Services Disabled',
          'Device location (GPS) is turned off. Please enable location services in your device settings and try again.',
          [{ text: 'OK' }]
        );
        return;
      }

      // 2. Request foreground location permission
      console.log('[Location] Requesting foreground permissions...');
      const permResult = await Location.requestForegroundPermissionsAsync();
      console.log(`[Location] Permission: ${permResult.status} (granted=${permResult.granted})`);

      if (permResult.status !== 'granted' && !permResult.granted) {
        setLocationStatus('error');
        Alert.alert(
          'Location Permission Denied',
          'Unable to detect location. Please enter it manually or allow location access in your device settings.',
          [{ text: 'OK' }]
        );
        return;
      }

      // 3. Obtain current position with timeout & fallback (High -> Balanced -> LastKnown)
      console.log('[Location] Obtaining position...');
      let coords: Location.LocationObjectCoords | null = null;

      // Primary attempt: High accuracy (10s timeout)
      try {
        const pos = await withTimeout(
          Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }),
          10000,
          'High accuracy timeout'
        );
        coords = pos.coords;
      } catch (highErr) {
        // Secondary attempt: Balanced accuracy (8s timeout)
        try {
          const pos = await withTimeout(
            Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }),
            8000,
            'Balanced accuracy timeout'
          );
          coords = pos.coords;
        } catch (balErr) {
          // Tertiary attempt: Last known position
          try {
            const lastKnown = await Location.getLastKnownPositionAsync({});
            if (lastKnown && lastKnown.coords) {
              coords = lastKnown.coords;
            }
          } catch (lastErr) {
            console.warn('[Location] Last known position lookup failed:', lastErr);
          }
        }
      }

      if (!coords) {
        setLocationStatus('error');
        Alert.alert(
          'GPS Unavailable',
          'Unable to obtain your current position. Please ensure GPS is enabled or enter the location manually.',
          [{ text: 'OK' }]
        );
        return;
      }

      console.log(`[Location] Coordinates: lat=${coords.latitude}, lon=${coords.longitude}`);

      // Accuracy guard: warn if accuracy is extremely poor (> 2000 meters)
      if (coords.accuracy !== null && coords.accuracy !== undefined && coords.accuracy > 2000) {
        setLocationStatus('error');
        Alert.alert(
          'Poor GPS Accuracy',
          `Location accuracy is very low (±${Math.round(coords.accuracy / 1000)} km). Please enter the location manually.`,
          [{ text: 'OK' }]
        );
        return;
      }

      // 4. Reverse geocode coordinates to a human-readable address
      console.log('[Location] Reverse geocoding: started');
      let resolvedAddress = '';

      try {
        const places = await withTimeout(
          Location.reverseGeocodeAsync({
            latitude: coords.latitude,
            longitude: coords.longitude,
          }),
          8000,
          'Reverse geocode timeout'
        );

        console.log('[Location] Geocoded address:', JSON.stringify(places?.[0] ?? null));

        if (places && places.length > 0) {
          resolvedAddress = formatGeocodedAddress(places[0]);
        }
      } catch (geoErr) {
        console.warn('[Location] Reverse geocoding failed or timed out:', geoErr);
      }

      console.log(`[Location] Formatted address: ${resolvedAddress || '(empty)'}`);

      if (resolvedAddress) {
        console.log(`[Location] Setting location field: ${resolvedAddress}`);
        setLocation(resolvedAddress);
        setLocationStatus('success');
      } else {
        // Reverse geocoding produced no address (e.g. offline or geocoding service unavailable)
        console.log('[Location] Reverse geocoding produced no address (offline or unavailable)');
        setLocationStatus('error');
        Alert.alert(
          'Could Not Fetch Address',
          'Location detected, but reverse geocoding is unavailable. Please enter the location manually.',
          [{ text: 'OK' }]
        );
      }
    } catch (unhandledErr: any) {
      console.error('[Location] Unhandled error in location detection:', unhandledErr);
      setLocationStatus('error');
      Alert.alert(
        'Location Detection Error',
        unhandledErr?.message || 'Unable to detect location. Please enter it manually.',
        [{ text: 'OK' }]
      );
    } finally {
      locationLoadingRef.current = false;
      setLocationLoading(false);
    }
  };

  /**
   * Saves a local draft and navigates to CaptureImages so the officer can
   * capture package images offline immediately.
   */
  const saveOfflineDraftAndCapture = async (errorMsg?: string) => {
    const clientDraftId = clientDraftIdRef.current || draftStorage.generateClientDraftId();
    const combinedNotes = [
      manufacturer ? `Manufacturer: ${manufacturer}` : '',
      source ? `Source: ${source}` : '',
      inspectionContext ? `Context: ${inspectionContext}` : '',
      notes ? `Notes: ${notes}` : '',
    ]
      .filter(Boolean)
      .join(' | ');

    const localDraft = {
      clientDraftId,
      productName: productName.trim(),
      brandName: brandName.trim(),
      category,
      location: location.trim(),
      batchNumber: batchNumber.trim() || undefined,
      manufacturer: manufacturer.trim() || undefined,
      source: source.trim() || undefined,
      inspectionContext,
      notes: combinedNotes || undefined,
      images: [],
      // LOCAL_CAPTURE: officer is still in the capture phase
      status: 'LOCAL_CAPTURE' as const,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      syncError: errorMsg,
    };

    await draftStorage.saveDraft(localDraft);

    // Navigate directly to CaptureImages so the officer can capture images offline.
    // Using clientDraftId as the inspectionId signals the draft path throughout.
    navigation.navigate('CaptureImages', {
      inspectionId: clientDraftId,
      inspectionNumber: undefined,
    });
  };

  const handleContinue = async () => {
    // Hard guard: bail immediately if a submission is already in-flight
    if (submittingRef.current) return;

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

    submittingRef.current = true;
    setLoading(true);

    try {
      // ── Proactive offline detection ────────────────────────────────────────
      // Check connectivity BEFORE attempting the API call. If we are already
      // offline, create a local draft immediately without a failed network request.
      if (!networkService.isOnline()) {
        await saveOfflineDraftAndCapture('Device is offline. Inspection saved locally.');
        return;
      }

      const combinedNotes = [
        manufacturer ? `Manufacturer: ${manufacturer}` : '',
        source ? `Source: ${source}` : '',
        inspectionContext ? `Context: ${inspectionContext}` : '',
        notes ? `Notes: ${notes}` : '',
      ]
        .filter(Boolean)
        .join(' | ');

      const inspection = await api.createInspection({
        client_draft_id: clientDraftIdRef.current,
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
      const errorMsg = String(err?.message || '');
      const isNetworkError =
        !networkService.isOnline() ||
        errorMsg.includes('Network') ||
        errorMsg.includes('Failed to fetch') ||
        errorMsg.includes('Network request failed') ||
        errorMsg.includes('502') ||
        errorMsg.includes('503') ||
        errorMsg.includes('504');

      if (isNetworkError) {
        // Reactive fallback: API call failed due to connectivity loss mid-request
        await saveOfflineDraftAndCapture(errorMsg);
      } else {
        Alert.alert('Error', err.message || 'Failed to create inspection record.');
      }
    } finally {
      submittingRef.current = false;
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
    <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
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
          style={{ flex: 1 }}
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
                <Text style={styles.fieldLabel}>
                  Location <Text style={{ color: colors.error }}>*</Text>
                </Text>
                <TextInput
                  style={styles.textInput}
                  value={location}
                  onChangeText={(text) => {
                    setLocation(text);
                    // If the user edits manually after auto-fill, reset success badge
                    if (locationStatus === 'success') setLocationStatus('idle');
                  }}
                  placeholder="e.g. Sector 4 Market"
                  placeholderTextColor={colors.outline}
                  testID="location-input"
                  accessibilityLabel="Location"
                />
                {/* Use Current Location button */}
                <TouchableOpacity
                  style={[
                    styles.locationBtn,
                    locationLoading && styles.locationBtnDisabled,
                    locationStatus === 'success' && styles.locationBtnSuccess,
                  ]}
                  onPress={handleUseCurrentLocation}
                  disabled={locationLoading}
                  activeOpacity={0.8}
                  testID="use-location-btn"
                >
                  {locationLoading ? (
                    <>
                      <ActivityIndicator size="small" color={colors.primary} style={{ marginRight: 6 }} />
                      <Text style={styles.locationBtnText}>Detecting Location...</Text>
                    </>
                  ) : locationStatus === 'success' ? (
                    <>
                      <MaterialIcons name="check-circle" size={15} color={colors.statusGreenText ?? '#16a34a'} style={{ marginRight: 5 }} />
                      <Text style={[styles.locationBtnText, styles.locationBtnTextSuccess]}>Current Location Used</Text>
                    </>
                  ) : (
                    <>
                      <MaterialIcons name="my-location" size={15} color={colors.primary} style={{ marginRight: 5 }} />
                      <Text style={styles.locationBtnText}>Use Current Location</Text>
                    </>
                  )}
                </TouchableOpacity>
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
  // ── Location button ───────────────────────────────────────────────────────
  locationBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    paddingVertical: 7,
    paddingHorizontal: 12,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    backgroundColor: colors.surfaceContainerLow,
    marginTop: 4,
  },
  locationBtnDisabled: {
    opacity: 0.6,
  },
  locationBtnSuccess: {
    borderColor: '#bbf7d0',
    backgroundColor: '#f0fdf4',
  },
  locationBtnText: {
    ...typography.bodySm,
    fontSize: 13,
    color: colors.primary,
    fontWeight: '500',
  },
  locationBtnTextSuccess: {
    color: '#15803d',
  },
});
