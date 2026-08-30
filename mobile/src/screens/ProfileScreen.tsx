import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  Alert,
  SafeAreaView,
  Modal,
  TextInput,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { BottomNav } from '../components/BottomNav';
import { ProfileAvatar } from '../components/ProfileAvatar';
import { authStorage } from '../services/authStorage';
import { api } from '../services/api';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

export const ProfileScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [profile, setProfile] = useState<any>(null);
  const [drawerVisible, setDrawerVisible] = useState(false);

  // Email Edit Modal State
  const [emailModalVisible, setEmailModalVisible] = useState(false);
  const [emailInput, setEmailInput] = useState('');
  const [emailError, setEmailError] = useState<string | null>(null);
  const [savingEmail, setSavingEmail] = useState(false);

  // Phone Edit Modal State
  const [phoneModalVisible, setPhoneModalVisible] = useState(false);
  const [phoneInput, setPhoneInput] = useState('');
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [savingPhone, setSavingPhone] = useState(false);

  // Change Password Modal State
  const [passwordModalVisible, setPasswordModalVisible] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [savingPassword, setSavingPassword] = useState(false);
  const [passwordUpdatedTime, setPasswordUpdatedTime] = useState('Updated 30 days ago');

  // Sign Out Confirmation Modal State
  const [signOutModalVisible, setSignOutModalVisible] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    // Load profile: first from local storage, then revalidate from server
    const loadProfile = async () => {
      const localProf = await authStorage.getProfile();
      if (localProf) setProfile(localProf);
      try {
        const serverProf = await api.getProfile();
        if (serverProf) {
          setProfile(serverProf);
          await authStorage.saveProfile(serverProf);
        }
      } catch (err) {
        // Server validation failed — use local cache
        console.warn('Profile revalidation failed, using local cache.');
      }
    };
    loadProfile();
  }, []);

  const officerName = profile?.full_name || 'Inspector';
  const officerId = profile?.officer_id || 'DOCA-INSP-842';
  const officerRole = profile?.designation || 'Inspector (Legal Metrology)';
  const officerZone = profile?.zone || 'Northern Zone - Delhi HQ';
  const officerEmail = profile?.email || '';
  const officerPhone = profile?.phone || '';

  // Email Edit Handlers
  const handleOpenEmailModal = () => {
    setEmailInput(officerEmail);
    setEmailError(null);
    setEmailModalVisible(true);
  };

  const handleSaveEmail = async () => {
    const trimmed = emailInput.trim();
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (!trimmed) {
      setEmailError('Email address cannot be empty.');
      return;
    }
    if (!emailRegex.test(trimmed)) {
      setEmailError('Please enter a valid email address.');
      return;
    }

    setSavingEmail(true);
    setEmailError(null);

    try {
      // Persist to backend (real database)
      const updatedProfile = await api.updateProfile({ email: trimmed }) as any;
      // Update local cache with server response
      await authStorage.saveProfile(updatedProfile);
      setProfile(updatedProfile);
      setEmailModalVisible(false);
      Alert.alert('Success', 'Email address updated successfully.');
    } catch (err: any) {
      setEmailError(err.message || 'Failed to update email address.');
    } finally {
      setSavingEmail(false);
    }
  };

  // Phone Edit Handlers
  const handleOpenPhoneModal = () => {
    setPhoneInput(officerPhone);
    setPhoneError(null);
    setPhoneModalVisible(true);
  };

  const handleSavePhone = async () => {
    const trimmed = phoneInput.trim();
    const phoneDigits = trimmed.replace(/\D/g, '');

    if (!trimmed) {
      setPhoneError('Phone number cannot be empty.');
      return;
    }
    if (phoneDigits.length < 7 || phoneDigits.length > 15) {
      setPhoneError('Please enter a valid phone number (7 to 15 digits).');
      return;
    }

    setSavingPhone(true);
    setPhoneError(null);

    try {
      // Persist to backend (real database)
      const updatedProfile = await api.updateProfile({ phone: trimmed }) as any;
      await authStorage.saveProfile(updatedProfile);
      setProfile(updatedProfile);
      setPhoneModalVisible(false);
      Alert.alert('Success', 'Phone number updated successfully.');
    } catch (err: any) {
      setPhoneError(err.message || 'Failed to update phone number.');
    } finally {
      setSavingPhone(false);
    }
  };

  // Change Password Handlers
  const handleOpenPasswordModal = () => {
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setPasswordError(null);
    setShowCurrentPassword(false);
    setShowNewPassword(false);
    setShowConfirmPassword(false);
    setPasswordModalVisible(true);
  };

  const handleSavePassword = async () => {
    if (!currentPassword.trim()) {
      setPasswordError('Please enter your current password.');
      return;
    }
    if (!newPassword.trim()) {
      setPasswordError('Please enter a new password.');
      return;
    }
    if (newPassword.length < 6) {
      setPasswordError('New password must be at least 6 characters long.');
      return;
    }
    if (newPassword === currentPassword) {
      setPasswordError('New password cannot be the same as current password.');
      return;
    }
    if (!confirmPassword.trim()) {
      setPasswordError('Please confirm your new password.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError('New password and confirmation do not match.');
      return;
    }

    setSavingPassword(true);
    setPasswordError(null);

    try {
      // Persist to backend (real Bcrypt verification + hash update)
      await api.changePassword({
        current_password: currentPassword.trim(),
        new_password: newPassword.trim(),
      });

      setPasswordUpdatedTime('Updated just now');
      setPasswordModalVisible(false);
      Alert.alert('Password Updated', 'Your security password has been changed successfully.');
    } catch (err: any) {
      setPasswordError(err.message || 'Failed to update password. Check your current password.');
    } finally {
      setSavingPassword(false);
    }
  };

  const executeSignOut = async () => {
    try {
      setSigningOut(true);
      await authStorage.clear();
      setSignOutModalVisible(false);
      navigation.reset({
        index: 0,
        routes: [{ name: 'Login' }],
      });
    } catch (e) {
      console.error('Sign out error:', e);
      setSignOutModalVisible(false);
      navigation.navigate('Login');
    } finally {
      setSigningOut(false);
    }
  };

  const handleSignOut = () => {
    setSignOutModalVisible(true);
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        {/* Stitch TopAppBar Header */}
        <View style={styles.topHeader}>
          <TouchableOpacity
            style={styles.headerIconButton}
            activeOpacity={0.7}
            onPress={() => {
              console.log('ProfileScreen: Hamburger menu pressed');
              setDrawerVisible(true);
            }}
            hitSlop={{ top: 15, bottom: 15, left: 15, right: 15 }}
          >
            <MaterialIcons name="menu" size={24} color={colors.onSurfaceVariant} />
          </TouchableOpacity>
          <Text style={styles.headerTitle} numberOfLines={1} ellipsizeMode="tail">
            LEGAL METROLOGY
          </Text>
          <TouchableOpacity
            style={styles.headerIconButton}
            activeOpacity={0.7}
            onPress={() => Alert.alert('Inspector', `${officerName}\nID: ${officerId}`)}
          >
            <ProfileAvatar size={36} />
          </TouchableOpacity>
        </View>

        <ScrollView
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Section 1: Profile Header Card */}
          <View style={styles.profileHeaderCard}>
            <ProfileAvatar size={88} iconSize={52} />

            <View style={styles.profileMetaContainer}>
              <Text style={styles.profileNameText} numberOfLines={2}>
                {officerName}
              </Text>
              <Text style={styles.profileIdText}>ID: {officerId}</Text>

              {/* Responsive Tags Container: allows wrapping and proper alignment on all screen sizes */}
              <View style={styles.profileTagsRow}>
                <View style={styles.profileTagItem}>
                  <MaterialIcons name="badge" size={16} color={colors.secondary} />
                  <Text style={styles.profileTagText} numberOfLines={1}>
                    {officerRole}
                  </Text>
                </View>
                <View style={styles.profileTagItem}>
                  <MaterialIcons name="domain" size={16} color={colors.secondary} />
                  <Text style={styles.profileTagText} numberOfLines={1}>
                    Legal Metrology Dept.
                  </Text>
                </View>
              </View>
            </View>
          </View>

          {/* Section 2: Account Information Card */}
          <View style={styles.cardSection}>
            <View style={styles.cardHeader}>
              <Text style={styles.cardHeaderText}>ACCOUNT INFORMATION</Text>
            </View>

            <View style={styles.cardBody}>
              {/* Email Address */}
              <View style={[styles.infoRow, styles.rowBorder]}>
                <View style={styles.infoTextCol}>
                  <Text style={styles.fieldLabelCaps}>EMAIL ADDRESS</Text>
                  <Text style={styles.fieldValueMd} numberOfLines={1} ellipsizeMode="middle">
                    {officerEmail}
                  </Text>
                </View>
                <TouchableOpacity
                  style={styles.editIconBtn}
                  onPress={handleOpenEmailModal}
                  activeOpacity={0.7}
                  hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                >
                  <MaterialIcons name="edit" size={20} color={colors.primary} />
                </TouchableOpacity>
              </View>

              {/* Phone Number */}
              <View style={[styles.infoRow, styles.rowBorder]}>
                <View style={styles.infoTextCol}>
                  <Text style={styles.fieldLabelCaps}>PHONE NUMBER</Text>
                  <Text style={styles.fieldValueMd} numberOfLines={1}>
                    {officerPhone}
                  </Text>
                </View>
                <TouchableOpacity
                  style={styles.editIconBtn}
                  onPress={handleOpenPhoneModal}
                  activeOpacity={0.7}
                  hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                >
                  <MaterialIcons name="edit" size={20} color={colors.primary} />
                </TouchableOpacity>
              </View>

              {/* Jurisdiction Region */}
              <View style={styles.infoRow}>
                <View style={styles.infoTextCol}>
                  <Text style={styles.fieldLabelCaps}>JURISDICTION REGION</Text>
                  <Text style={styles.fieldValueMd} numberOfLines={2}>
                    {officerZone}
                  </Text>
                </View>
              </View>
            </View>
          </View>

          {/* Section 3: Security Card */}
          <View style={styles.cardSection}>
            <View style={styles.cardHeader}>
              <Text style={styles.cardHeaderText}>SECURITY</Text>
            </View>

            <View style={styles.cardBody}>
              {/* Change Password */}
              <TouchableOpacity
                style={[styles.actionRow, styles.rowBorder]}
                onPress={handleOpenPasswordModal}
                activeOpacity={0.7}
              >
                <View style={styles.actionLeft}>
                  <MaterialIcons name="password" size={22} color={colors.onSurfaceVariant} />
                  <View style={styles.actionTextCol}>
                    <Text style={styles.fieldValueMd}>Change Password</Text>
                    <Text style={styles.fieldValueSm}>{passwordUpdatedTime}</Text>
                  </View>
                </View>
                <MaterialIcons name="chevron-right" size={22} color={colors.onSurfaceVariant} />
              </TouchableOpacity>

              {/* Last Login */}
              <View style={[styles.actionRow, styles.rowBorder]}>
                <View style={styles.actionLeft}>
                  <MaterialIcons name="history" size={22} color={colors.onSurfaceVariant} />
                  <View style={styles.actionTextCol}>
                    <Text style={styles.fieldValueMd}>Last Login</Text>
                    <Text style={styles.fieldValueSm}>Today, 08:45 AM from Current Device</Text>
                  </View>
                </View>
              </View>

              {/* Sign Out Button */}
              <View style={styles.signOutBtnContainer}>
                <TouchableOpacity
                  style={styles.signOutButton}
                  onPress={handleSignOut}
                  activeOpacity={0.85}
                >
                  <MaterialIcons name="logout" size={18} color={colors.error} />
                  <Text style={styles.signOutText}>SIGN OUT</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>

          {/* Section 4: Application Info Card */}
          <View style={styles.appInfoCard}>
            <View style={styles.appInfoRow}>
              <Text style={styles.appInfoLabel}>App Version</Text>
              <Text style={styles.appInfoValue}>v2.4.1 (Build 890)</Text>
            </View>
            <View style={[styles.appInfoRow, { borderBottomWidth: 0, paddingBottom: 0 }]}>
              <Text style={styles.appInfoLabel}>System Build</Text>
              <Text style={styles.appInfoBuildValue}>SIH 2026 Prototype</Text>
            </View>
          </View>

          {/* Section 5: Legal / Decision Support Note */}
          <View style={styles.legalNoteBanner}>
            <MaterialIcons name="info" size={20} color={colors.statusAmberText} style={{ marginTop: 1 }} />
            <Text style={styles.legalNoteText}>
              This is an AI-assisted inspection and decision-support system. Final inspection decisions are made by the authorized inspector.
            </Text>
          </View>
        </ScrollView>

        {/* Navigation Drawer Modal */}
        <Modal
          visible={drawerVisible}
          transparent
          animationType="fade"
          onRequestClose={() => setDrawerVisible(false)}
        >
          <View style={styles.drawerOverlay}>
            <TouchableOpacity
              style={styles.drawerBackdrop}
              activeOpacity={1}
              onPress={() => setDrawerVisible(false)}
            />
            <View style={styles.drawerContainer}>
              {/* Drawer Header */}
              <View style={styles.drawerHeader}>
                <Text style={styles.drawerBrandTitle}>LEGAL METROLOGY</Text>
                <View style={styles.drawerUserBox}>
                  <ProfileAvatar size={40} />
                  <View style={styles.drawerUserMeta}>
                    <Text style={styles.drawerUserName}>{officerName}</Text>
                    <Text style={styles.drawerUserRole}>{officerRole}</Text>
                    <Text style={styles.drawerUserId}>ID: {officerId}</Text>
                  </View>
                </View>
              </View>

              {/* Drawer Links */}
              <View style={styles.drawerLinks}>
                <TouchableOpacity
                  style={styles.drawerLinkItem}
                  onPress={() => {
                    setDrawerVisible(false);
                    navigation.navigate('Dashboard');
                  }}
                >
                  <MaterialIcons name="home" size={22} color={colors.primary} />
                  <Text style={styles.drawerLinkLabel}>Dashboard</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.drawerLinkItem}
                  onPress={() => {
                    setDrawerVisible(false);
                    navigation.navigate('NewInspection');
                  }}
                >
                  <MaterialIcons name="add-circle" size={22} color={colors.primary} />
                  <Text style={styles.drawerLinkLabel}>New Inspection</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.drawerLinkItem}
                  onPress={() => {
                    setDrawerVisible(false);
                    navigation.navigate('DraftOffline');
                  }}
                >
                  <MaterialIcons name="drafts" size={22} color={colors.primary} />
                  <Text style={styles.drawerLinkLabel}>Draft Inspections</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.drawerLinkItem}
                  onPress={() => {
                    setDrawerVisible(false);
                    navigation.navigate('ReportsList');
                  }}
                >
                  <MaterialIcons name="description" size={22} color={colors.primary} />
                  <Text style={styles.drawerLinkLabel}>Reports Archive</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[styles.drawerLinkItem, styles.drawerLinkItemActive]}
                  onPress={() => {
                    setDrawerVisible(false);
                  }}
                >
                  <MaterialIcons name="person" size={22} color={colors.onPrimary} />
                  <Text style={[styles.drawerLinkLabel, styles.drawerLinkLabelActive]}>Profile</Text>
                </TouchableOpacity>
              </View>

              {/* Drawer Footer */}
              <View style={styles.drawerFooter}>
                <Text style={styles.drawerFooterText}>Legal Metrology Dept.</Text>
                <Text style={styles.drawerFooterVersion}>v1.0.0 (SIH 2026)</Text>
              </View>
            </View>
          </View>
        </Modal>

        {/* Edit Email Modal */}
        <Modal visible={emailModalVisible} transparent animationType="fade">
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
            style={styles.modalOverlay}
          >
            <View style={styles.modalContent}>
              <View style={styles.modalHeader}>
                <Text style={typography.sectionHeader}>Edit Email Address</Text>
                <TouchableOpacity onPress={() => setEmailModalVisible(false)}>
                  <MaterialIcons name="close" size={22} color={colors.onSurfaceVariant} />
                </TouchableOpacity>
              </View>

              <View style={styles.modalInputGroup}>
                <Text style={typography.labelCaps}>Email Address</Text>
                <TextInput
                  style={styles.modalTextInput}
                  value={emailInput}
                  onChangeText={(text) => {
                    setEmailInput(text);
                    if (emailError) setEmailError(null);
                  }}
                  placeholder="e.g. rajesh.kumar@lm.gov.in"
                  placeholderTextColor={colors.outline}
                  keyboardType="email-address"
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>

              {emailError ? (
                <View style={styles.errorBanner}>
                  <MaterialIcons name="error" size={16} color={colors.statusRedText} />
                  <Text style={styles.errorText}>{emailError}</Text>
                </View>
              ) : null}

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={styles.modalCancelBtn}
                  onPress={() => setEmailModalVisible(false)}
                  disabled={savingEmail}
                >
                  <Text style={styles.modalCancelText}>Cancel</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.modalSaveBtn}
                  onPress={handleSaveEmail}
                  disabled={savingEmail}
                  activeOpacity={0.85}
                >
                  {savingEmail ? (
                    <ActivityIndicator size="small" color={colors.onPrimary} />
                  ) : (
                    <Text style={styles.modalSaveText}>Save Email</Text>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          </KeyboardAvoidingView>
        </Modal>

        {/* Edit Phone Modal */}
        <Modal visible={phoneModalVisible} transparent animationType="fade">
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
            style={styles.modalOverlay}
          >
            <View style={styles.modalContent}>
              <View style={styles.modalHeader}>
                <Text style={typography.sectionHeader}>Edit Phone Number</Text>
                <TouchableOpacity onPress={() => setPhoneModalVisible(false)}>
                  <MaterialIcons name="close" size={22} color={colors.onSurfaceVariant} />
                </TouchableOpacity>
              </View>

              <View style={styles.modalInputGroup}>
                <Text style={typography.labelCaps}>Phone Number</Text>
                <TextInput
                  style={styles.modalTextInput}
                  value={phoneInput}
                  onChangeText={(text) => {
                    setPhoneInput(text);
                    if (phoneError) setPhoneError(null);
                  }}
                  placeholder="e.g. +91 98765 43210"
                  placeholderTextColor={colors.outline}
                  keyboardType="phone-pad"
                />
              </View>

              {phoneError ? (
                <View style={styles.errorBanner}>
                  <MaterialIcons name="error" size={16} color={colors.statusRedText} />
                  <Text style={styles.errorText}>{phoneError}</Text>
                </View>
              ) : null}

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={styles.modalCancelBtn}
                  onPress={() => setPhoneModalVisible(false)}
                  disabled={savingPhone}
                >
                  <Text style={styles.modalCancelText}>Cancel</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.modalSaveBtn}
                  onPress={handleSavePhone}
                  disabled={savingPhone}
                  activeOpacity={0.85}
                >
                  {savingPhone ? (
                    <ActivityIndicator size="small" color={colors.onPrimary} />
                  ) : (
                    <Text style={styles.modalSaveText}>Save Phone</Text>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          </KeyboardAvoidingView>
        </Modal>

        {/* Change Password Modal */}
        <Modal visible={passwordModalVisible} transparent animationType="fade">
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
            style={styles.modalOverlay}
          >
            <View style={styles.modalContent}>
              <View style={styles.modalHeader}>
                <Text style={typography.sectionHeader}>Change Security Password</Text>
                <TouchableOpacity onPress={() => setPasswordModalVisible(false)}>
                  <MaterialIcons name="close" size={22} color={colors.onSurfaceVariant} />
                </TouchableOpacity>
              </View>

              {/* Current Password */}
              <View style={styles.modalInputGroup}>
                <Text style={typography.labelCaps}>Current Password</Text>
                <View style={styles.passwordFieldRow}>
                  <TextInput
                    style={[styles.modalTextInput, styles.passwordInput]}
                    value={currentPassword}
                    onChangeText={(text) => {
                      setCurrentPassword(text);
                      if (passwordError) setPasswordError(null);
                    }}
                    placeholder="••••••••"
                    placeholderTextColor={colors.outline}
                    secureTextEntry={!showCurrentPassword}
                  />
                  <TouchableOpacity
                    style={styles.passwordEyeBtn}
                    onPress={() => setShowCurrentPassword(!showCurrentPassword)}
                    hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                  >
                    <MaterialIcons
                      name={showCurrentPassword ? 'visibility-off' : 'visibility'}
                      size={20}
                      color={colors.onSurfaceVariant}
                    />
                  </TouchableOpacity>
                </View>
              </View>

              {/* New Password */}
              <View style={styles.modalInputGroup}>
                <Text style={typography.labelCaps}>New Password</Text>
                <View style={styles.passwordFieldRow}>
                  <TextInput
                    style={[styles.modalTextInput, styles.passwordInput]}
                    value={newPassword}
                    onChangeText={(text) => {
                      setNewPassword(text);
                      if (passwordError) setPasswordError(null);
                    }}
                    placeholder="Min 6 characters"
                    placeholderTextColor={colors.outline}
                    secureTextEntry={!showNewPassword}
                  />
                  <TouchableOpacity
                    style={styles.passwordEyeBtn}
                    onPress={() => setShowNewPassword(!showNewPassword)}
                    hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                  >
                    <MaterialIcons
                      name={showNewPassword ? 'visibility-off' : 'visibility'}
                      size={20}
                      color={colors.onSurfaceVariant}
                    />
                  </TouchableOpacity>
                </View>
              </View>

              {/* Confirm New Password */}
              <View style={styles.modalInputGroup}>
                <Text style={typography.labelCaps}>Confirm New Password</Text>
                <View style={styles.passwordFieldRow}>
                  <TextInput
                    style={[styles.modalTextInput, styles.passwordInput]}
                    value={confirmPassword}
                    onChangeText={(text) => {
                      setConfirmPassword(text);
                      if (passwordError) setPasswordError(null);
                    }}
                    placeholder="Re-enter new password"
                    placeholderTextColor={colors.outline}
                    secureTextEntry={!showConfirmPassword}
                  />
                  <TouchableOpacity
                    style={styles.passwordEyeBtn}
                    onPress={() => setShowConfirmPassword(!showConfirmPassword)}
                    hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                  >
                    <MaterialIcons
                      name={showConfirmPassword ? 'visibility-off' : 'visibility'}
                      size={20}
                      color={colors.onSurfaceVariant}
                    />
                  </TouchableOpacity>
                </View>
              </View>

              {passwordError ? (
                <View style={styles.errorBanner}>
                  <MaterialIcons name="error" size={16} color={colors.statusRedText} />
                  <Text style={styles.errorText}>{passwordError}</Text>
                </View>
              ) : null}

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={styles.modalCancelBtn}
                  onPress={() => setPasswordModalVisible(false)}
                  disabled={savingPassword}
                >
                  <Text style={styles.modalCancelText}>Cancel</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.modalSaveBtn}
                  onPress={handleSavePassword}
                  disabled={savingPassword}
                  activeOpacity={0.85}
                >
                  {savingPassword ? (
                    <ActivityIndicator size="small" color={colors.onPrimary} />
                  ) : (
                    <Text style={styles.modalSaveText}>Update Password</Text>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          </KeyboardAvoidingView>
        </Modal>

        {/* Sign Out Confirmation Modal */}
        <Modal
          visible={signOutModalVisible}
          transparent
          animationType="fade"
          onRequestClose={() => {
            if (!signingOut) setSignOutModalVisible(false);
          }}
        >
          <View style={styles.modalOverlay}>
            <View style={styles.modalContent}>
              <View style={styles.modalHeader}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <MaterialIcons name="logout" size={22} color={colors.error} />
                  <Text style={typography.sectionHeader}>Sign Out</Text>
                </View>
                <TouchableOpacity
                  onPress={() => setSignOutModalVisible(false)}
                  disabled={signingOut}
                  hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                >
                  <MaterialIcons name="close" size={22} color={colors.onSurfaceVariant} />
                </TouchableOpacity>
              </View>

              <View style={{ marginVertical: 14 }}>
                <Text style={[typography.bodyMd, { color: colors.onSurface, lineHeight: 20 }]}>
                  Are you sure you want to end your inspection session and sign out from this field terminal?
                </Text>
              </View>

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={styles.modalCancelBtn}
                  onPress={() => setSignOutModalVisible(false)}
                  disabled={signingOut}
                >
                  <Text style={styles.modalCancelText}>Cancel</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[styles.modalSaveBtn, { backgroundColor: colors.error }]}
                  onPress={executeSignOut}
                  disabled={signingOut}
                  activeOpacity={0.85}
                >
                  {signingOut ? (
                    <ActivityIndicator size="small" color={colors.onError} />
                  ) : (
                    <Text style={styles.modalSaveText}>Sign Out</Text>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

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
  headerIconButton: {
    padding: 6,
    borderRadius: borderRadius.round,
  },
  headerTitle: {
    ...typography.headlineLg,
    fontSize: 18,
    fontWeight: '700',
    color: colors.primary,
    letterSpacing: -0.2,
    flex: 1,
    textAlign: 'center',
    marginHorizontal: 8,
  },
  scrollContent: {
    paddingHorizontal: spacing.marginX,
    paddingTop: spacing.stackMd,
    paddingBottom: 24,
    gap: spacing.stackMd,
  },
  profileHeaderCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.marginX,
    alignItems: 'center',
    gap: spacing.stackSm,
  },
  avatarContainer: {
    width: 88,
    height: 88,
    borderRadius: 44,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    backgroundColor: colors.surfaceContainerLow,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  avatarWrapper: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  profileMetaContainer: {
    alignItems: 'center',
    gap: 2,
    width: '100%',
  },
  profileNameText: {
    ...typography.headlineLg,
    fontSize: 20,
    lineHeight: 28,
    fontWeight: '600',
    color: colors.primary,
    textAlign: 'center',
  },
  profileIdText: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.onSurfaceVariant,
    marginTop: spacing.tight,
    textAlign: 'center',
  },
  profileTagsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    alignItems: 'center',
    gap: spacing.stackSm,
    marginTop: spacing.stackSm,
    width: '100%',
  },
  profileTagItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.tight,
    paddingHorizontal: 4,
    paddingVertical: 2,
  },
  profileTagText: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.secondary,
  },
  cardSection: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    overflow: 'hidden',
  },
  cardHeader: {
    paddingHorizontal: spacing.marginX,
    paddingVertical: spacing.stackSm,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    backgroundColor: colors.surfaceBright,
  },
  cardHeaderText: {
    ...typography.sectionHeader,
    fontSize: 16,
    lineHeight: 24,
    fontWeight: '600',
    color: colors.primary,
  },
  cardBody: {
    flexDirection: 'column',
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.marginX,
    paddingVertical: spacing.stackMd,
    gap: 8,
  },
  rowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  infoTextCol: {
    flex: 1,
  },
  fieldLabelCaps: {
    ...typography.labelCaps,
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 0.24,
    color: colors.onSurfaceVariant,
  },
  fieldValueMd: {
    ...typography.bodyMd,
    fontSize: 14,
    lineHeight: 20,
    color: colors.onSurface,
    marginTop: spacing.tight,
  },
  fieldValueSm: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.onSurfaceVariant,
    marginTop: spacing.tight,
  },
  editIconBtn: {
    padding: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.marginX,
    paddingVertical: spacing.stackMd,
    gap: 8,
  },
  actionLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.stackMd,
    flex: 1,
  },
  actionTextCol: {
    flex: 1,
  },
  signOutBtnContainer: {
    paddingHorizontal: spacing.marginX,
    paddingVertical: spacing.stackMd,
  },
  signOutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceContainerHighest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    paddingVertical: spacing.stackSm,
    paddingHorizontal: spacing.gutter,
    gap: spacing.tight,
  },
  signOutText: {
    ...typography.labelCaps,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '600',
    color: colors.error,
  },
  appInfoCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.marginX,
    gap: spacing.stackMd,
  },
  appInfoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    paddingBottom: spacing.stackSm,
  },
  appInfoLabel: {
    ...typography.bodySm,
    fontSize: 13,
    color: colors.secondary,
  },
  appInfoValue: {
    ...typography.bodyMd,
    fontSize: 14,
    color: colors.onSurface,
  },
  appInfoBuildValue: {
    ...typography.bodyMd,
    fontSize: 14,
    fontWeight: '600',
    color: colors.primary,
  },
  legalNoteBanner: {
    backgroundColor: colors.statusAmberBg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    padding: spacing.stackMd,
    flexDirection: 'row',
    gap: spacing.stackSm,
    alignItems: 'flex-start',
    marginBottom: spacing.stackMd,
  },
  legalNoteText: {
    ...typography.caption,
    fontSize: 12,
    lineHeight: 16,
    color: colors.onSurface,
    flex: 1,
    flexShrink: 1,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.gutter,
  },
  modalContent: {
    width: '100%',
    maxWidth: 400,
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    padding: spacing.marginX,
    gap: spacing.stackMd,
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    paddingBottom: spacing.stackSm,
  },
  modalInputGroup: {
    gap: 4,
  },
  modalTextInput: {
    backgroundColor: colors.surfaceBright,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    paddingHorizontal: 12,
    paddingVertical: 8,
    ...typography.bodyMd,
    color: colors.onSurface,
  },
  passwordFieldRow: {
    position: 'relative',
    justifyContent: 'center',
  },
  passwordInput: {
    paddingRight: 40,
  },
  passwordEyeBtn: {
    position: 'absolute',
    right: 12,
  },
  errorBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.statusRedBg,
    borderWidth: 1,
    borderColor: 'rgba(183, 28, 28, 0.2)',
    borderRadius: borderRadius.lg,
    padding: 8,
    gap: 6,
  },
  errorText: {
    ...typography.bodySm,
    color: colors.statusRedText,
    flex: 1,
    fontSize: 12,
  },
  modalActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 8,
    marginTop: spacing.tight,
  },
  modalCancelBtn: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    alignItems: 'center',
    justifyContent: 'center',
  },
  modalCancelText: {
    ...typography.bodySm,
    fontWeight: '600',
    color: colors.secondary,
  },
  modalSaveBtn: {
    backgroundColor: colors.primary,
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: borderRadius.lg,
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: 100,
  },
  modalSaveText: {
    ...typography.bodySm,
    fontWeight: '700',
    color: colors.onPrimary,
  },
  drawerOverlay: {
    flex: 1,
    flexDirection: 'row',
    zIndex: 9999,
  },
  drawerBackdrop: {
    position: 'absolute',
    top: 0,
    left: 0,
    width: '100%',
    height: '100%',
    backgroundColor: 'rgba(0, 0, 0, 0.45)',
  },
  drawerContainer: {
    width: '75%',
    maxWidth: 300,
    height: '100%',
    backgroundColor: colors.surfaceContainerLowest,
    shadowColor: '#000',
    shadowOffset: { width: 4, height: 0 },
    shadowOpacity: 0.15,
    shadowRadius: 10,
    elevation: 20,
    paddingTop: Platform.OS === 'ios' ? 50 : 20,
    justifyContent: 'space-between',
    zIndex: 10000,
  },
  drawerHeader: {
    paddingHorizontal: 20,
    paddingVertical: 24,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  drawerBrandTitle: {
    ...typography.headlineLg,
    color: colors.primary,
    fontSize: 18,
    fontWeight: '800',
    letterSpacing: 0.5,
    marginBottom: 18,
  },
  drawerUserBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  drawerUserMeta: {
    flex: 1,
  },
  drawerUserName: {
    ...typography.bodyMd,
    fontWeight: '700',
    color: colors.onSurface,
  },
  drawerUserRole: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
    marginTop: 1,
  },
  drawerUserId: {
    ...typography.caption,
    fontSize: 10,
    color: colors.outline,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
    marginTop: 2,
  },
  drawerLinks: {
    flex: 1,
    paddingTop: 16,
    paddingHorizontal: 10,
    gap: 8,
  },
  drawerLinkItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 12,
    borderRadius: borderRadius.lg,
    gap: 12,
  },
  drawerLinkItemActive: {
    backgroundColor: colors.primary,
  },
  drawerLinkLabel: {
    ...typography.bodyMd,
    fontWeight: '500',
    color: colors.onSurfaceVariant,
  },
  drawerLinkLabelActive: {
    color: colors.onPrimary,
    fontWeight: '700',
  },
  drawerFooter: {
    paddingHorizontal: 20,
    paddingVertical: 18,
    borderTopWidth: 1,
    borderTopColor: colors.borderSubtle,
    backgroundColor: colors.surfaceContainerLow,
  },
  drawerFooterText: {
    ...typography.caption,
    color: colors.onSurfaceVariant,
    fontWeight: '600',
  },
  drawerFooterVersion: {
    ...typography.caption,
    fontSize: 10,
    color: colors.outline,
    marginTop: 2,
  },
});
