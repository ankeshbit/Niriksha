import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Image,
  ActivityIndicator,
  Alert,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as ImagePicker from 'expo-image-picker';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { api, getApiBaseUrl, classifyFetchError } from '../services/api';
import { draftStorage } from '../services/draftStorage';
import { checkImageQuality, getQualityLabel, isQualityBlocking, ImageQualityResult } from '../services/imageQualityService';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

// ─── Local image slot state (includes quality result) ─────────────────────────

interface ImageSlot {
  id: string;
  view_type: string;
  file_path: string;
  is_local?: boolean;
  quality_status?: string;    // server-side: 'GOOD' | 'WARNING' | 'POOR'
  qualityResult?: ImageQualityResult; // on-device quality result
  qualityChecking?: boolean;  // true while local check is running
}

export const CaptureImagesScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'CaptureImages'>>();
  const { inspectionId, inspectionNumber } = route.params;

  const isDraftMode = Boolean(inspectionId && inspectionId.startsWith('draft-'));

  const [images, setImages] = useState<ImageSlot[]>([]);
  const [uploadingSlot, setUploadingSlot] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Monotonic version token per slot to prevent stale async quality results and race conditions
  const slotVersions = React.useRef<Record<string, number>>({ front: 0, back: 0, side: 0 });

  const loadImages = async () => {
    try {
      if (isDraftMode) {
        const draft = await draftStorage.getDraft(inspectionId);
        if (draft && draft.images) {
          setImages(
            draft.images.map((img) => ({
              id: `${draft.clientDraftId}-${img.viewType}`,
              view_type: img.viewType,
              file_path: img.uri,
              is_local: true,
              quality_status: img.qualityResult
                ? (img.qualityResult.isAcceptable ? 'GOOD' : 'POOR')
                : 'GOOD',
              qualityResult: img.qualityResult,
            }))
          );
        }
        return;
      }
      const data = await api.getInspectionImages(inspectionId);
      setImages(data || []);
    } catch (err) {
      console.error('Failed to load images:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadImages();
  }, [inspectionId]);

  const handleDeleteImage = async (viewType: 'front' | 'back' | 'side', imgData?: ImageSlot) => {
    // Invalidate any in-flight quality check or upload for this slot
    slotVersions.current[viewType] = (slotVersions.current[viewType] || 0) + 1;

    // Immediately remove from UI state
    setImages((prev) => prev.filter((img) => img.view_type !== viewType));

    if (uploadingSlot === viewType) {
      setUploadingSlot(null);
    }

    if (isDraftMode) {
      try {
        await draftStorage.removeDraftImage(inspectionId, viewType);
      } catch (err) {
        console.error('[CaptureImagesScreen] Failed to remove draft image:', err);
      }
      return;
    }

    // Online mode: delete from backend
    try {
      if (imgData?.id && !imgData.is_local) {
        await api.deleteImage(imgData.id);
      } else {
        await api.deleteImageBySlot(inspectionId, viewType);
      }
    } catch (err) {
      console.warn('[CaptureImagesScreen] Backend delete by ID failed, attempting slot deletion:', err);
      try {
        await api.deleteImageBySlot(inspectionId, viewType);
      } catch (slotErr) {
        console.error('[CaptureImagesScreen] Backend delete by slot failed:', slotErr);
      }
    }
  };

  // ─── Image picker ──────────────────────────────────────────────────────────

  const handlePickImage = async (viewType: 'front' | 'back' | 'side') => {
    if (Platform.OS === 'web') {
      await launchGallery(viewType);
      return;
    }

    Alert.alert(
      'Upload Package Image',
      `Select source for ${viewType.toUpperCase()} panel:`,
      [
        {
          text: 'Camera',
          onPress: () => launchCamera(viewType),
        },
        {
          text: 'Gallery / Files',
          onPress: () => launchGallery(viewType),
        },
        { text: 'Cancel', style: 'cancel' },
      ]
    );
  };

  const launchCamera = async (viewType: string) => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission Denied', 'Camera access is required to photograph package labels.');
      return;
    }

    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.9,
      allowsEditing: true,
    });

    if (!result.canceled && result.assets && result.assets[0]) {
      const asset = result.assets[0];
      await processPickedImage(asset.uri, viewType, asset.width || 0, asset.height || 0);
    }
  };

  const launchGallery = async (viewType: string) => {
    if (Platform.OS !== 'web') {
      const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission Denied', 'Gallery access is required to select package photos.');
        return;
      }
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.9,
      allowsEditing: true,
    });

    if (!result.canceled && result.assets && result.assets[0]) {
      const asset = result.assets[0];
      await processPickedImage(asset.uri, viewType, asset.width || 0, asset.height || 0);
    }
  };

  // ─── Core image processing pipeline ───────────────────────────────────────

  /**
   * After a photo is picked:
   * 1. Save the image to local storage immediately (preserve original).
   * 2. Show "Checking image quality..." spinner in the slot.
   * 3. Run on-device quality check (no network, no API call).
   * 4. Update the slot with the quality result.
   * 5. If online inspection: also upload to server.
   */
  const processPickedImage = async (
    uri: string,
    viewType: string,
    width: number,
    height: number
  ) => {
    slotVersions.current[viewType] = (slotVersions.current[viewType] || 0) + 1;
    const currentToken = slotVersions.current[viewType];

    setUploadingSlot(viewType);

    try {
      if (isDraftMode) {
        // ── Draft (offline) path ────────────────────────────────────────────
        // FIX-RC-BLOB: On web, expo-image-picker returns a blob: URL.
        // Blob URLs expire/revoke when components unmount or navigate.
        // Immediately convert to a durable base64 Data URL before saving to draft storage.
        let storageUri = uri;
        if (Platform.OS === 'web' && uri.startsWith('blob:')) {
          try {
            const blobRes = await fetch(uri);
            const blobData = await blobRes.blob();
            storageUri = await new Promise<string>((resolve, reject) => {
              const reader = new FileReader();
              reader.onloadend = () => {
                if (typeof reader.result === 'string') {
                  resolve(reader.result);
                } else {
                  reject(new Error('FileReader did not return a string'));
                }
              };
              reader.onerror = reject;
              reader.readAsDataURL(blobData);
            });
          } catch (blobConvErr) {
            console.warn('[CaptureImagesScreen] Blob to Data URL conversion error, falling back to blob uri:', blobConvErr);
          }
        }

        if (slotVersions.current[viewType] !== currentToken) return;

        // Step 1: Save image locally immediately (preserve durable URI)
        await draftStorage.addDraftImage(inspectionId, {
          viewType: viewType as 'front' | 'back' | 'side',
          uri: storageUri,
        });

        if (slotVersions.current[viewType] !== currentToken) return;

        // Optimistically show the slot while quality check runs
        setImages((prev) => {
          const filtered = prev.filter((img) => img.view_type !== viewType);
          return [
            ...filtered,
            {
              id: `${inspectionId}-${viewType}`,
              view_type: viewType,
              file_path: storageUri,
              is_local: true,
              qualityChecking: true,
              quality_status: 'GOOD',
            },
          ];
        });

        // Step 2: Run on-device quality check (100% offline)
        const qualityResult = await checkImageQuality(storageUri, width, height);

        if (slotVersions.current[viewType] !== currentToken) return;

        // Step 3: Save quality result alongside the image
        await draftStorage.addDraftImageWithQuality(inspectionId, {
          viewType: viewType as 'front' | 'back' | 'side',
          uri: storageUri,
          qualityResult,
        });

        if (slotVersions.current[viewType] !== currentToken) return;

        // Step 4: Update UI with quality result
        setImages((prev) => {
          const filtered = prev.filter((img) => img.view_type !== viewType);
          return [
            ...filtered,
            {
              id: `${inspectionId}-${viewType}`,
              view_type: viewType,
              file_path: storageUri,
              is_local: true,
              qualityChecking: false,
              quality_status: qualityResult.isAcceptable ? 'GOOD' : 'POOR',
              qualityResult,
            },
          ];
        });

        return;
      }

      // ── Online path: upload to server ─────────────────────────────────────

      // Run local quality check first (saves network round trip for obvious duds)
      const qualityResult = await checkImageQuality(uri, width, height);

      if (slotVersions.current[viewType] !== currentToken) return;

      // Show checking state
      setImages((prev) => {
        const filtered = prev.filter((img) => img.view_type !== viewType);
        return [
          ...filtered,
          {
            id: `${inspectionId}-${viewType}`,
            view_type: viewType,
            file_path: uri,
            is_local: true,
            qualityChecking: false,
            quality_status: qualityResult.isAcceptable ? 'GOOD' : 'POOR',
            qualityResult,
          },
        ];
      });

      const formData = new FormData();
      const filename = uri.split('/').pop() || `${viewType}_panel.jpg`;
      const match = /\.(\w+)$/.exec(filename);
      const type = match ? `image/${match[1]}` : 'image/jpeg';

      if (Platform.OS === 'web') {
        // FIX-RC-3: On web, expo-image-picker returns a blob: URL.
        // Blob URLs can be revoked or expire after the first read, causing
        // a "Failed to fetch" error. This is a CLIENT-SIDE issue, not a
        // network connectivity failure. Handle it separately with a clear message.
        let blob: Blob;
        try {
          const blobResponse = await fetch(uri);
          if (!blobResponse.ok) {
            throw new Error(`Blob fetch returned status ${blobResponse.status}`);
          }
          blob = await blobResponse.blob();
        } catch (blobErr: any) {
          const classified = classifyFetchError(blobErr, uri);
          const msg =
            classified.type === 'BLOB_FETCH_ERROR'
              ? 'Could not read the selected image. Please tap the slot and select the image again.'
              : classified.userMessage;
          if (Platform.OS === 'web') {
            alert(msg);
          } else {
            Alert.alert('Image Error', msg);
          }
          // Remove the slot so the user can re-select
          if (slotVersions.current[viewType] === currentToken) {
            setImages((prev) => prev.filter((img) => img.view_type !== viewType));
          }
          return;
        }
        formData.append('file', blob, filename);
      } else {
        formData.append('file', {
          uri: Platform.OS === 'android' ? uri : uri.replace('file://', ''),
          name: filename,
          type,
        } as any);
      }
      formData.append('view_type', viewType);

      const uploadedImage = await api.uploadImage(inspectionId, formData);

      if (slotVersions.current[viewType] !== currentToken) return;

      if (uploadedImage && uploadedImage.id) {
        setImages((prev) => {
          const filtered = prev.filter((img) => img.view_type !== viewType);
          return [
            ...filtered,
            {
              id: uploadedImage.id,
              view_type: viewType,
              file_path: uploadedImage.file_path || uri,
              is_local: false,
              qualityChecking: false,
              quality_status: uploadedImage.quality_status || (qualityResult.isAcceptable ? 'GOOD' : 'POOR'),
              qualityResult,
            },
          ];
        });
      } else {
        await loadImages();
      }
    } catch (err: any) {
      if (slotVersions.current[viewType] === currentToken) {
        const classified = classifyFetchError(err);
        const msg = classified.userMessage || err.message || 'Could not process image.';
        if (Platform.OS === 'web') {
          alert(msg);
        } else {
          Alert.alert('Error', msg);
        }
      }
    } finally {
      if (slotVersions.current[viewType] === currentToken) {
        setUploadingSlot(null);
      }
    }
  };

  useEffect(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      (window as any).__NIRIKSHA_PICK_IMAGE__ = async (
        viewType: 'front' | 'back' | 'side',
        uri: string,
        width = 800,
        height = 600
      ) => {
        await processPickedImage(uri, viewType, width, height);
      };
      (window as any).__NIRIKSHA_DELETE_IMAGE__ = async (
        viewType: 'front' | 'back' | 'side'
      ) => {
        const target = images.find((img) => img.view_type === viewType);
        await handleDeleteImage(viewType, target);
      };
    }
  }, [inspectionId, isDraftMode, images]);

  // ─── Derived state ─────────────────────────────────────────────────────────

  const frontImg = images.find((img) => img.view_type === 'front');
  const backImg = images.find((img) => img.view_type === 'back');
  const sideImg = images.find((img) => img.view_type === 'side' || img.view_type === 'panel');

  const activeImages = [frontImg, backImg, sideImg].filter(Boolean) as ImageSlot[];

  const baseUrl = getApiBaseUrl();

  // Warning if any active image has a quality issue (server-side OR on-device)
  const hasWarning = activeImages.some(
    (img) =>
      img.quality_status === 'WARNING' ||
      img.quality_status === 'POOR' ||
      (img.qualityResult && !img.qualityResult.isAcceptable)
  );
  const hasAtLeastOneImage = activeImages.length > 0;

  // Count active images with quality issues for the warning bar
  const blurryImages = activeImages.filter(
    (img) =>
      img.quality_status === 'POOR' ||
      (img.qualityResult && !img.qualityResult.isAcceptable)
  );

  // ─── Slot rendering ────────────────────────────────────────────────────────

  const renderSlot = (
    title: string,
    viewType: 'front' | 'back' | 'side',
    imgData?: ImageSlot,
    isRequired: boolean = false
  ) => {
    const isUploading = uploadingSlot === viewType;
    const isChecking = Boolean(imgData?.qualityChecking);

    // Determine quality state
    const hasOnDeviceResult = Boolean(imgData?.qualityResult);
    const onDeviceBlurry = hasOnDeviceResult && !imgData!.qualityResult!.isAcceptable;
    const serverWarn =
      imgData?.quality_status === 'WARNING' || imgData?.quality_status === 'POOR';
    const isWarn = onDeviceBlurry || serverWarn;

    const qualityLabel = imgData?.qualityResult
      ? getQualityLabel(imgData.qualityResult)
      : imgData?.quality_status === 'GOOD'
      ? 'Image quality acceptable'
      : imgData?.quality_status === 'WARNING' || imgData?.quality_status === 'POOR'
      ? 'Image appears blurry'
      : 'Image quality acceptable';

    // Loading / quality-checking state
    if (isUploading || isChecking) {
      return (
        <View style={styles.slotCard}>
          <View style={styles.slotHeader}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Text style={styles.slotHeaderLabel}>{title}</Text>
              <View style={[styles.requirementBadge, isRequired ? styles.requiredBadge : styles.optionalBadge]}>
                <Text style={[styles.requirementBadgeText, isRequired ? styles.requiredBadgeText : styles.optionalBadgeText]}>
                  {isRequired ? 'REQUIRED' : 'OPTIONAL'}
                </Text>
              </View>
            </View>
          </View>
          <View style={styles.uploadingBox}>
            <ActivityIndicator size="small" color={colors.primary} />
            <Text style={styles.uploadingText}>
              {isChecking ? 'Checking image quality...' : 'Assessing image quality (OpenCV)...'}
            </Text>
          </View>
        </View>
      );
    }

    // Empty slot
    if (!imgData) {
      return (
        <TouchableOpacity
          style={styles.emptySlotCard}
          onPress={() => handlePickImage(viewType)}
          activeOpacity={0.7}
        >
          <View style={styles.emptySlotHeader}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Text style={styles.emptySlotHeaderLabel}>{title}</Text>
              <View style={[styles.requirementBadge, isRequired ? styles.requiredBadge : styles.optionalBadge]}>
                <Text style={[styles.requirementBadgeText, isRequired ? styles.requiredBadgeText : styles.optionalBadgeText]}>
                  {isRequired ? 'REQUIRED' : 'OPTIONAL'}
                </Text>
              </View>
            </View>
          </View>
          <View style={styles.emptySlotContent}>
            <MaterialIcons name="add-a-photo" size={28} color={colors.secondary} />
            <Text style={styles.emptySlotText}>Tap to Add Image</Text>
            <Text style={styles.emptySlotSubtext}>
              {isRequired ? 'Mandatory package view' : 'Capture side view if needed'}
            </Text>
          </View>
        </TouchableOpacity>
      );
    }

    const imageSourceUri =
      imgData.is_local ||
      imgData.file_path.startsWith('data:') ||
      imgData.file_path.startsWith('blob:') ||
      imgData.file_path.startsWith('file:') ||
      imgData.file_path.startsWith('http')
        ? imgData.file_path
        : `${baseUrl}${imgData.file_path}`;

    return (
      <View style={[styles.slotCard, isWarn && styles.slotCardWarn]}>
        <View style={styles.slotHeader}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Text style={styles.slotHeaderLabel}>{title}</Text>
            <View style={[styles.requirementBadge, isRequired ? styles.requiredBadge : styles.optionalBadge]}>
              <Text style={[styles.requirementBadgeText, isRequired ? styles.requiredBadgeText : styles.optionalBadgeText]}>
                {isRequired ? 'REQUIRED' : 'OPTIONAL'}
              </Text>
            </View>
          </View>
          {isWarn ? (
            <View style={styles.warnChip}>
              <MaterialIcons name="warning" size={14} color={colors.statusAmberText} />
              <Text style={styles.warnChipText}>Image appears blurry</Text>
            </View>
          ) : (
            <View style={styles.goodChip}>
              <MaterialIcons name="check-circle" size={14} color={colors.statusGreenText} />
              <Text style={styles.goodChipText}>Image quality acceptable</Text>
            </View>
          )}
        </View>

        {/* Quality status line */}
        <View style={[styles.qualityStatusBar, isWarn ? styles.qualityStatusBarWarn : styles.qualityStatusBarGood]}>
          <MaterialIcons
            name={isWarn ? 'error-outline' : 'check-circle'}
            size={13}
            color={isWarn ? colors.statusAmberText : colors.statusGreenText}
          />
          <Text style={[styles.qualityStatusText, isWarn ? styles.qualityStatusTextWarn : styles.qualityStatusTextGood]}>
            {isWarn ? (imgData?.qualityResult?.reason || 'Image appears blurry. Please capture the image again.') : qualityLabel}
          </Text>
        </View>

        <View style={styles.slotBody}>
          <View style={[styles.thumbnailBox, isWarn && styles.thumbnailWarn]}>
            <Image
              source={{ uri: imageSourceUri }}
              style={styles.thumbnailImage}
              resizeMode="cover"
            />
          </View>

          <View style={styles.slotActions}>
            <TouchableOpacity
              style={[styles.retakeBtn, isWarn && styles.retakeBtnWarn]}
              onPress={() => handlePickImage(viewType)}
              activeOpacity={0.8}
            >
              <Text style={[styles.retakeBtnText, isWarn && styles.retakeBtnTextWarn]}>
                {isWarn ? 'Capture Again' : 'Retake'}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.deleteBtn}
              onPress={() => handleDeleteImage(viewType, imgData)}
              activeOpacity={0.8}
            >
              <MaterialIcons name="delete" size={18} color={colors.secondary} />
            </TouchableOpacity>
          </View>
        </View>
      </View>
    );
  };

  // ─── Continue handler ──────────────────────────────────────────────────────

  const hasRequiredImages = Boolean(frontImg && backImg);

  const handleContinue = () => {
    if (!hasRequiredImages) {
      const msg = 'Please capture both Front and Back package images before proceeding. Side image is optional.';
      if (Platform.OS === 'web') {
        alert(msg);
      } else {
        Alert.alert('Required Images', msg);
      }
      return;
    }

    if (blurryImages.length > 0) {
      const msg = 'Image appears blurry. Please capture the image again before continuing.';
      if (Platform.OS === 'web') {
        alert(msg);
      } else {
        Alert.alert('Image Appears Blurry', msg);
      }
      return;
    }

    if (isDraftMode) {
      // Update draft status to READY_FOR_SYNC before going to the offline screen
      draftStorage.updateDraftStatus(inspectionId, 'READY_FOR_SYNC').catch(() => {});
      navigation.navigate('DraftOffline', { clientDraftId: inspectionId });
      return;
    }

    navigation.navigate('Analyzing', {
      inspectionId,
      inspectionNumber,
    });
  };

  // ─── Render ────────────────────────────────────────────────────────────────

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        {/* Stitch TopAppBar Header */}
        <View style={styles.topHeader}>
          <TouchableOpacity
            style={styles.backButton}
            onPress={() => navigation.goBack()}
            activeOpacity={0.7}
          >
            <MaterialIcons name="arrow-back" size={24} color={colors.primary} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Step 2 of 3</Text>
          <View style={{ width: 40 }} />
        </View>

        <ScrollView style={{ flex: 1 }} contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          {/* Section Header */}
          <View style={styles.instructionSection}>
            <Text style={styles.instructionTitle}>Capture Package Images</Text>
            <Text style={styles.instructionSubtitle}>
              Capture clear images of Front and Back label areas (Side is optional).{' '}
              {isDraftMode ? 'Each image is quality-checked on your device.' : 'Ensure accurate processing.'}
            </Text>
          </View>

          {Platform.OS === 'web' && (
            <TouchableOpacity
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                backgroundColor: '#EEF2FF',
                borderColor: colors.primary,
                borderWidth: 1,
                borderRadius: borderRadius.DEFAULT,
                paddingVertical: 10,
                paddingHorizontal: 16,
                marginBottom: 8,
              }}
              onPress={async () => {
                try {
                  setUploadingSlot('front');
                  const fetchAsDataUrl = async (url: string) => {
                    const res = await fetch(url);
                    const blob = await res.blob();
                    return new Promise<string>((resolve, reject) => {
                      const reader = new FileReader();
                      reader.onloadend = () => resolve(reader.result as string);
                      reader.onerror = reject;
                      reader.readAsDataURL(blob);
                    });
                  };
                  const baseUrl = getApiBaseUrl();
                  const frontData = await fetchAsDataUrl(`${baseUrl}/uploads/test_fixtures/front.jpg`);
                  await processPickedImage(frontData, 'front', 800, 600);
                  const backData = await fetchAsDataUrl(`${baseUrl}/uploads/test_fixtures/back.jpg`);
                  await processPickedImage(backData, 'back', 800, 600);
                } catch (e) {
                  console.error('Failed to attach test package images:', e);
                }
              }}
            >
              <MaterialIcons name="attachment" size={18} color={colors.primary} />
              <Text style={{ ...typography.labelCaps, color: colors.primary, fontWeight: '700' }}>
                Attach Real Test Package Images (Front & Back)
              </Text>
            </TouchableOpacity>
          )}

          {loading ? (
            <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
          ) : (
            <View style={styles.slotsContainer}>
              {renderSlot('FRONT IMAGE', 'front', frontImg, true)}
              {renderSlot('BACK IMAGE', 'back', backImg, true)}
              {renderSlot('SIDE IMAGE', 'side', sideImg, false)}
            </View>
          )}

          <View style={{ height: 120 }} />
        </ScrollView>

        {/* Bottom Actions & Status Container */}
        <View style={styles.bottomFixedContainer}>
          {hasWarning && (
            <View style={styles.warningStatusBar}>
              <MaterialIcons name="warning" size={18} color={colors.statusAmberText} style={{ marginTop: 1 }} />
              <View style={{ flex: 1 }}>
                <Text style={styles.warningStatusText}>
                  {blurryImages.length} image{blurryImages.length > 1 ? 's appear' : ' appears'} blurry. Please capture again before proceeding.
                </Text>
                <View style={styles.warningActionLinks}>
                  <TouchableOpacity onPress={() => {
                    // Scroll to first blurry image and trigger retake
                    const firstBlurry = blurryImages[0];
                    if (firstBlurry) {
                      handlePickImage(firstBlurry.view_type as 'front' | 'back' | 'side');
                    }
                  }}>
                    <Text style={styles.warningLinkText}>Capture Again</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </View>
          )}

          <View style={styles.bottomBtnRow}>
            <TouchableOpacity
              style={[
                styles.continueBtn,
                hasWarning ? styles.continueBtnWarning : styles.continueBtnPrimary,
                (!hasRequiredImages || hasWarning) && styles.continueBtnDisabled,
              ]}
              onPress={handleContinue}
              disabled={!hasRequiredImages || hasWarning}
              activeOpacity={0.85}
            >
              {hasWarning ? (
                <View style={styles.btnContentCol}>
                  <View style={styles.btnContentRow}>
                    <MaterialIcons name="warning" size={18} color={colors.onPrimary} />
                    <Text style={styles.continueBtnText}>Image Appears Blurry — Capture Again</Text>
                  </View>
                  <Text style={styles.continueBtnSubtext}>
                    {blurryImages.length} image{blurryImages.length > 1 ? 's need' : ' needs'} retake.
                  </Text>
                </View>
              ) : (
                <View style={styles.btnContentRow}>
                  <Text style={styles.continueBtnText}>
                    {!hasRequiredImages
                      ? 'Capture Front & Back to Continue'
                      : isDraftMode
                      ? 'Save Draft & Wait for Connection'
                      : 'Continue to Analysis'}
                  </Text>
                  <MaterialIcons name="arrow-forward" size={18} color={colors.onPrimary} />
                </View>
              )}
            </TouchableOpacity>
          </View>
        </View>
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
    textAlign: 'center',
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: spacing.gutter,
    paddingTop: spacing.stackMd,
    paddingBottom: 24,
    gap: spacing.stackMd,
  },
  instructionSection: {
    gap: 4,
    marginBottom: 4,
  },
  instructionTitle: {
    ...typography.sectionHeader,
    fontSize: 16,
    lineHeight: 24,
    fontWeight: '600',
    color: colors.primary,
  },
  instructionSubtitle: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.secondary,
  },
  slotsContainer: {
    gap: spacing.stackMd,
  },
  slotCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    overflow: 'hidden',
  },
  slotCardWarn: {
    borderColor: colors.statusAmberText,
  },
  slotHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.gutter,
    paddingVertical: spacing.stackSm,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  slotHeaderLabel: {
    ...typography.labelCaps,
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 0.5,
    fontWeight: '600',
    color: colors.primary,
  },
  requirementBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  requiredBadge: {
    backgroundColor: '#EEF2FF',
  },
  optionalBadge: {
    backgroundColor: '#F3F4F6',
  },
  requirementBadgeText: {
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  requiredBadgeText: {
    color: '#4F46E5',
  },
  optionalBadgeText: {
    color: '#6B7280',
  },
  qualityStatusBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.gutter,
    paddingVertical: 5,
    gap: 5,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  qualityStatusBarGood: {
    backgroundColor: colors.statusGreenBg,
  },
  qualityStatusBarWarn: {
    backgroundColor: colors.statusAmberBg,
  },
  qualityStatusText: {
    fontSize: 11,
    lineHeight: 15,
    flex: 1,
  },
  qualityStatusTextGood: {
    color: colors.statusGreenText,
    fontWeight: '500',
  },
  qualityStatusTextWarn: {
    color: colors.statusAmberText,
    fontWeight: '500',
  },
  goodChip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.statusGreenBg,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: borderRadius.DEFAULT,
    gap: 4,
  },
  goodChipText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.statusGreenText,
  },
  warnChip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.statusAmberBg,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: borderRadius.DEFAULT,
    gap: 4,
  },
  warnChipText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.statusAmberText,
  },
  slotBody: {
    padding: spacing.gutter,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  thumbnailBox: {
    width: 100,
    height: 75,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    backgroundColor: colors.surfaceContainer,
    overflow: 'hidden',
  },
  thumbnailWarn: {
    borderColor: colors.statusAmberText,
    opacity: 0.85,
  },
  thumbnailImage: {
    width: '100%',
    height: '100%',
  },
  slotActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flex: 1,
    justifyContent: 'flex-end',
  },
  retakeBtn: {
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    borderColor: colors.primary,
    backgroundColor: colors.surfaceContainerLowest,
  },
  retakeBtnWarn: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  retakeBtnText: {
    ...typography.bodySm,
    fontSize: 13,
    color: colors.primary,
    fontWeight: '600',
  },
  retakeBtnTextWarn: {
    color: colors.onPrimary,
  },
  deleteBtn: {
    padding: 8,
    borderRadius: borderRadius.DEFAULT,
  },
  emptySlotCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    overflow: 'hidden',
  },
  emptySlotHeader: {
    paddingHorizontal: spacing.gutter,
    paddingVertical: spacing.stackSm,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderStyle: 'dashed',
    borderBottomColor: colors.borderSubtle,
  },
  emptySlotHeaderLabel: {
    ...typography.labelCaps,
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 0.5,
    fontWeight: '600',
    color: colors.secondary,
  },
  emptySlotContent: {
    padding: 24,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  emptySlotText: {
    ...typography.bodySm,
    fontSize: 13,
    fontWeight: '500',
    color: colors.secondary,
  },
  emptySlotSubtext: {
    ...typography.caption,
    fontSize: 11,
    lineHeight: 15,
    color: colors.outline,
    marginTop: 2,
  },
  uploadingBox: {
    padding: 24,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  uploadingText: {
    ...typography.bodySm,
    color: colors.primary,
  },
  bottomFixedContainer: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: colors.surfaceContainerLowest,
    borderTopWidth: 1,
    borderTopColor: colors.borderSubtle,
    elevation: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: -3 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
  },
  warningStatusBar: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: colors.statusAmberBg,
    paddingHorizontal: spacing.gutter,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    gap: 8,
  },
  warningStatusText: {
    ...typography.caption,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '600',
    color: colors.statusAmberText,
  },
  warningActionLinks: {
    flexDirection: 'row',
    gap: 16,
    marginTop: 4,
  },
  warningLinkText: {
    ...typography.labelCaps,
    fontSize: 11,
    fontWeight: '700',
    color: colors.statusAmberText,
    textDecorationLine: 'underline',
  },
  bottomBtnRow: {
    padding: spacing.gutter,
    backgroundColor: colors.surface,
  },
  continueBtn: {
    width: '100%',
    paddingVertical: 12,
    borderRadius: borderRadius.DEFAULT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  continueBtnPrimary: {
    backgroundColor: colors.primaryContainer,
  },
  continueBtnWarning: {
    backgroundColor: '#E8590C',
  },
  continueBtnDisabled: {
    opacity: 0.5,
  },
  btnContentRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  btnContentCol: {
    alignItems: 'center',
    gap: 2,
  },
  continueBtnText: {
    ...typography.sectionHeader,
    fontSize: 16,
    lineHeight: 22,
    color: colors.onPrimary,
    fontWeight: '600',
  },
  continueBtnSubtext: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onPrimary,
    opacity: 0.85,
  },
});
