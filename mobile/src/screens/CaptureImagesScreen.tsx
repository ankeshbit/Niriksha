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
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { AppHeader } from '../components/AppHeader';
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
      setImages(data);
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

  const renderSlot = (title: string, viewType: 'front' | 'back' | 'side', imgData?: any) => {
    const isUploading = uploadingSlot === viewType;

    return (
      <View style={styles.slotCard}>
        <View style={styles.slotHeader}>
          <Text style={typography.labelCaps}>{title}</Text>
          {imgData ? (
            <View
              style={[
                styles.qualityChip,
                imgData.quality_status === 'GOOD'
                  ? styles.qualityGood
                  : imgData.quality_status === 'WARNING'
                  ? styles.qualityWarn
                  : styles.qualityBad,
              ]}
            >
              <MaterialIcons
                name={
                  imgData.quality_status === 'GOOD'
                    ? 'check-circle'
                    : imgData.quality_status === 'WARNING'
                    ? 'warning'
                    : 'error'
                }
                size={14}
                color={
                  imgData.quality_status === 'GOOD'
                    ? colors.statusGreenText
                    : imgData.quality_status === 'WARNING'
                    ? colors.statusAmberText
                    : colors.statusRedText
                }
              />
              <Text
                style={[
                  styles.qualityText,
                  {
                    color:
                      imgData.quality_status === 'GOOD'
                        ? colors.statusGreenText
                        : imgData.quality_status === 'WARNING'
                        ? colors.statusAmberText
                        : colors.statusRedText,
                  },
                ]}
              >
                {imgData.quality_status === 'GOOD'
                  ? `Good Quality (${Math.round(imgData.quality_score * 100)}%)`
                  : imgData.quality_status === 'WARNING'
                  ? `Warning (${Math.round(imgData.quality_score * 100)}%)`
                  : 'Blurry / Low Score'}
              </Text>
            </View>
          ) : null}
        </View>

        {isUploading ? (
          <View style={styles.uploadingBox}>
            <ActivityIndicator size="small" color={colors.primary} />
            <Text style={styles.uploadingText}>Assessing image quality (OpenCV)...</Text>
          </View>
        ) : imgData ? (
          <View style={styles.imagePreviewContainer}>
            <Image
              source={{ uri: `${baseUrl}${imgData.file_path}` }}
              style={styles.previewImage}
              resizeMode="cover"
            />
            <TouchableOpacity
              style={styles.retakeButton}
              onPress={() => handlePickImage(viewType)}
              activeOpacity={0.8}
            >
              <MaterialIcons name="photo-camera" size={16} color={colors.primary} />
              <Text style={styles.retakeText}>Retake / Replace</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <TouchableOpacity
            style={styles.emptySlot}
            onPress={() => handlePickImage(viewType)}
            activeOpacity={0.7}
          >
            <MaterialIcons name="add-a-photo" size={32} color={colors.primary} />
            <Text style={styles.addPhotoText}>Tap to Capture / Select {title}</Text>
            <Text style={styles.addPhotoSubtext}>Ensure clear lighting and legible text</Text>
          </TouchableOpacity>
        )}
      </View>
    );
  };

  const hasAtLeastOneImage = images.length > 0;

  return (
    <View style={styles.container}>
      <AppHeader
        title="CAPTURE IMAGES"
        subtitle={`Step 2 of 3: ${inspectionNumber || 'Package Photography'}`}
        showBack={true}
        onBackPress={() => navigation.goBack()}
      />

      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Quality Guidelines Card */}
        <View style={styles.guidelinesCard}>
          <MaterialIcons name="info" size={18} color={colors.primary} />
          <Text style={styles.guidelinesText}>
            Capture clear, focused images of the Principal Display Panel (PDP) and statutory declaration panels.
          </Text>
        </View>

        {loading ? (
          <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
        ) : (
          <>
            {renderSlot('FRONT PANEL (PDP)', 'front', frontImg)}
            {renderSlot('BACK PANEL (STATUTORY DETAILS)', 'back', backImg)}
            {renderSlot('SIDE / ADDITIONAL PANEL', 'side', sideImg)}

            <TouchableOpacity
              style={[
                styles.continueButton,
                !hasAtLeastOneImage && styles.continueButtonDisabled,
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
              <Text style={styles.continueButtonText}>Continue to OCR Analysis</Text>
              <MaterialIcons name="arrow-forward" size={18} color={colors.onPrimary} style={{ marginLeft: 6 }} />
            </TouchableOpacity>
          </>
        )}
      </ScrollView>
    </View>
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
    gap: spacing.stackMd,
  },
  guidelinesCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.stackMd,
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    gap: 8,
  },
  guidelinesText: {
    ...typography.caption,
    color: colors.onSurface,
    flex: 1,
  },
  slotCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.marginX,
    gap: spacing.stackSm,
  },
  slotHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  qualityChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    gap: 4,
  },
  qualityGood: {
    backgroundColor: colors.statusGreenBg,
    borderColor: colors.statusGreenText,
  },
  qualityWarn: {
    backgroundColor: colors.statusAmberBg,
    borderColor: colors.statusAmberText,
  },
  qualityBad: {
    backgroundColor: colors.statusRedBg,
    borderColor: colors.statusRedText,
  },
  qualityText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
  },
  emptySlot: {
    borderWidth: 1.5,
    borderStyle: 'dashed',
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.stackLg,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceBright,
    gap: 4,
  },
  addPhotoText: {
    ...typography.bodyMdMedium,
    color: colors.primary,
    marginTop: 4,
  },
  addPhotoSubtext: {
    ...typography.caption,
    color: colors.onSurfaceVariant,
  },
  uploadingBox: {
    padding: spacing.stackLg,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  uploadingText: {
    ...typography.bodySm,
    color: colors.primary,
  },
  imagePreviewContainer: {
    borderRadius: borderRadius.lg,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  previewImage: {
    width: '100%',
    height: 180,
    backgroundColor: colors.surfaceContainerHigh,
  },
  retakeButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    backgroundColor: colors.surfaceContainerLow,
    borderTopWidth: 1,
    borderTopColor: colors.borderSubtle,
    gap: 6,
  },
  retakeText: {
    ...typography.caption,
    fontWeight: '700',
    color: colors.primary,
  },
  continueButton: {
    backgroundColor: colors.primary,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: borderRadius.lg,
    marginTop: spacing.tight,
  },
  continueButtonDisabled: {
    opacity: 0.5,
  },
  continueButtonText: {
    ...typography.sectionHeader,
    color: colors.onPrimary,
  },
});
