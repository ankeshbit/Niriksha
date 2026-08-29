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
  SafeAreaView,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { api, getApiBaseUrl } from '../services/api';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const CaptureImagesScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'CaptureImages'>>();
  const { inspectionId, inspectionNumber } = route.params;

  const [images, setImages] = useState<any[]>([]);
  const [uploadingSlot, setUploadingSlot] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadImages = async () => {
    try {
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

  const handlePickImage = async (viewType: 'front' | 'back' | 'side') => {
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

    if (!result.canceled && result.assets[0]) {
      await uploadPickedImage(result.assets[0].uri, viewType);
    }
  };

  const launchGallery = async (viewType: string) => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission Denied', 'Gallery access is required to select package photos.');
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.9,
      allowsEditing: true,
    });

    if (!result.canceled && result.assets[0]) {
      await uploadPickedImage(result.assets[0].uri, viewType);
    }
  };

  const uploadPickedImage = async (uri: string, viewType: string) => {
    setUploadingSlot(viewType);
    try {
      const formData = new FormData();
      const filename = uri.split('/').pop() || `${viewType}_panel.jpg`;
      const match = /\.(\w+)$/.exec(filename);
      const type = match ? `image/${match[1]}` : 'image/jpeg';

      formData.append('file', {
        uri,
        name: filename,
        type,
      } as any);
      formData.append('view_type', viewType);

      await api.uploadImage(inspectionId, formData);
      await loadImages();
    } catch (err: any) {
      Alert.alert('Upload Failed', err.message || 'Could not upload image.');
    } finally {
      setUploadingSlot(null);
    }
  };

  const frontImg = images.find((img) => img.view_type === 'front');
  const backImg = images.find((img) => img.view_type === 'back');
  const sideImg = images.find((img) => img.view_type === 'side' || img.view_type === 'panel');

  const baseUrl = getApiBaseUrl();

  const hasWarning = images.some((img) => img.quality_status === 'WARNING' || img.quality_status === 'POOR');
  const hasAtLeastOneImage = images.length > 0;

  const renderSlot = (title: 'FRONT' | 'BACK' | 'SIDE', viewType: 'front' | 'back' | 'side', imgData?: any) => {
    const isUploading = uploadingSlot === viewType;
    const isWarn = imgData?.quality_status === 'WARNING' || imgData?.quality_status === 'POOR';

    if (isUploading) {
      return (
        <View style={styles.slotCard}>
          <View style={styles.slotHeader}>
            <Text style={styles.slotHeaderLabel}>{title}</Text>
          </View>
          <View style={styles.uploadingBox}>
            <ActivityIndicator size="small" color={colors.primary} />
            <Text style={styles.uploadingText}>Assessing image quality (OpenCV)...</Text>
          </View>
        </View>
      );
    }

    if (!imgData) {
      return (
        <TouchableOpacity
          style={styles.emptySlotCard}
          onPress={() => handlePickImage(viewType)}
          activeOpacity={0.7}
        >
          <View style={styles.emptySlotHeader}>
            <Text style={styles.emptySlotHeaderLabel}>{title}</Text>
          </View>
          <View style={styles.emptySlotContent}>
            <MaterialIcons name="add-a-photo" size={28} color={colors.secondary} />
            <Text style={styles.emptySlotText}>Tap to Add Image</Text>
          </View>
        </TouchableOpacity>
      );
    }

    return (
      <View style={[styles.slotCard, isWarn && styles.slotCardWarn]}>
        <View style={styles.slotHeader}>
          <Text style={styles.slotHeaderLabel}>{title}</Text>
          {isWarn ? (
            <View style={styles.warnChip}>
              <MaterialIcons name="warning" size={14} color={colors.statusAmberText} />
              <Text style={styles.warnChipText}>Blurry — Capture Again</Text>
            </View>
          ) : (
            <View style={styles.goodChip}>
              <MaterialIcons name="check-circle" size={14} color={colors.statusGreenText} />
              <Text style={styles.goodChipText}>Good Quality</Text>
            </View>
          )}
        </View>

        <View style={styles.slotBody}>
          <View style={[styles.thumbnailBox, isWarn && styles.thumbnailWarn]}>
            <Image
              source={{ uri: `${baseUrl}${imgData.file_path}` }}
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
                {isWarn ? 'Retake Now' : 'Retake'}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.deleteBtn}
              onPress={() => {
                Alert.alert('Remove Image', 'Are you sure you want to remove this photo?', [
                  { text: 'Cancel', style: 'cancel' },
                  {
                    text: 'Remove',
                    style: 'destructive',
                    onPress: () => {
                      setImages(images.filter((img) => img.id !== imgData.id));
                    },
                  },
                ]);
              }}
              activeOpacity={0.8}
            >
              <MaterialIcons name="delete" size={18} color={colors.secondary} />
            </TouchableOpacity>
          </View>
        </View>
      </View>
    );
  };

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

        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          {/* Section Header */}
          <View style={styles.instructionSection}>
            <Text style={styles.instructionTitle}>Capture Package Images</Text>
            <Text style={styles.instructionSubtitle}>
              Capture clear images of all required label areas to ensure accurate processing.
            </Text>
          </View>

          {loading ? (
            <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
          ) : (
            <View style={styles.slotsContainer}>
              {renderSlot('FRONT', 'front', frontImg)}
              {renderSlot('BACK', 'back', backImg)}
              {renderSlot('SIDE', 'side', sideImg)}
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
                  1 image requires attention before continuing. Back label is blurry.
                </Text>
                <View style={styles.warningActionLinks}>
                  <TouchableOpacity onPress={() => handlePickImage('back')}>
                    <Text style={styles.warningLinkText}>Retake Now</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={() =>
                      navigation.navigate('Analyzing', {
                        inspectionId,
                        inspectionNumber,
                      })
                    }
                  >
                    <Text style={styles.warningLinkText}>Continue Anyway</Text>
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
                !hasAtLeastOneImage && styles.continueBtnDisabled,
              ]}
              onPress={() => {
                if (!hasAtLeastOneImage) {
                  Alert.alert('Image Required', 'Please capture at least 1 package image before proceeding.');
                  return;
                }
                navigation.navigate('Analyzing', {
                  inspectionId,
                  inspectionNumber,
                });
              }}
              disabled={!hasAtLeastOneImage}
              activeOpacity={0.85}
            >
              {hasWarning ? (
                <View style={styles.btnContentCol}>
                  <View style={styles.btnContentRow}>
                    <MaterialIcons name="warning" size={18} color={colors.onPrimary} />
                    <Text style={styles.continueBtnText}>Continue with Warning</Text>
                  </View>
                  <Text style={styles.continueBtnSubtext}>1 image needs attention</Text>
                </View>
              ) : (
                <View style={styles.btnContentRow}>
                  <Text style={styles.continueBtnText}>Continue to Analysis</Text>
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
