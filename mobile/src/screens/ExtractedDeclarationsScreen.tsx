import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  Modal,
  TextInput,
  Alert,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { MaterialIcons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme/tokens';
import { BottomNav } from '../components/BottomNav';
import { ProfileAvatar } from '../components/ProfileAvatar';
import { api } from '../services/api';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/types';

const FIELD_LABELS: Record<string, string> = {
  commodity_name: 'Product Name',
  manufacturer_details: 'Manufacturer',
  manufacturer_address: 'Address',
  net_quantity: 'Net Quantity',
  mrp: 'MRP',
  date_of_manufacture_packing: 'Date of Packing',
  consumer_care_details: 'Consumer Care Information',
  country_of_origin: 'Country of Origin',
};

export const ExtractedDeclarationsScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'ExtractedDeclarations'>>();
  const { inspectionId, inspectionNumber } = route.params;
  const { width: windowWidth } = useWindowDimensions();
  const isNarrowScreen = windowWidth < 350;

  const [declarations, setDeclarations] = useState<any[]>([]);
  const [barcodesSummary, setBarcodesSummary] = useState<any | null>(null);
  const [validationMatrix, setValidationMatrix] = useState<any | null>(null);
  const [complianceSummary, setComplianceSummary] = useState<any | null>(null);
  const [showMatrixTable, setShowMatrixTable] = useState(true);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);

  // Edit Modal State
  const [editingDecl, setEditingDecl] = useState<any | null>(null);
  const [correctedValue, setCorrectedValue] = useState('');
  const [correctionReason, setCorrectionReason] = useState('');
  const [savingCorrection, setSavingCorrection] = useState(false);

  const loadDeclarations = async () => {
    try {
      const [declData, barcodeData, matrixData, summaryData] = await Promise.all([
        api.getDeclarations(inspectionId),
        api.getBarcodes(inspectionId).catch(() => null),
        api.getDeclarationValidation(inspectionId).catch(() => null),
        api.getComplianceSummary(inspectionId).catch(() => null),
      ]);
      setDeclarations(declData || []);
      setBarcodesSummary(barcodeData || null);
      setValidationMatrix(matrixData || null);
      setComplianceSummary(summaryData || null);
    } catch (err) {
      console.error('Failed to load declarations:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDeclarations();
  }, [inspectionId]);

  const openEditModal = (decl: any) => {
    setEditingDecl(decl);
    setCorrectedValue(decl.effective_value || decl.extracted_value || '');
    setCorrectionReason(decl.correction_reason || 'Verified on physical package label');
  };

  const handleSaveCorrection = async () => {
    if (!editingDecl) return;

    setSavingCorrection(true);
    try {
      await api.updateDeclaration(editingDecl.id, {
        corrected_value: correctedValue.trim(),
        verification_status: 'CORRECTED',
        correction_reason: correctionReason.trim() || undefined,
      });

      await loadDeclarations();
      setEditingDecl(null);
    } catch (err: any) {
      Alert.alert('Update Failed', err.message || 'Could not update declaration.');
    } finally {
      setSavingCorrection(false);
    }
  };

  const handleEvaluateRules = async () => {
    setEvaluating(true);
    try {
      await api.evaluateRules(inspectionId);
      navigation.navigate('Findings', {
        inspectionId,
        inspectionNumber,
      });
    } catch (err: any) {
      Alert.alert('Evaluation Failed', err.message || 'Rule evaluation failed.');
    } finally {
      setEvaluating(false);
    }
  };

  const todayStr = new Date().toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
      <View style={styles.container}>
        {/* Stitch TopAppBar Header */}
        <View style={styles.topHeader}>
          <View style={styles.headerLeft}>
            <TouchableOpacity
              style={styles.backButton}
              onPress={() => navigation.goBack()}
              activeOpacity={0.7}
            >
              <MaterialIcons name="arrow-back" size={24} color={colors.primary} />
            </TouchableOpacity>
            <View>
              <Text style={styles.headerTitle}>NiriKsha</Text>
              <Text style={styles.headerSubtitle}>
                {inspectionNumber ? `ID: ${inspectionNumber}` : (inspectionId ? `ID: ${inspectionId.substring(0, 8).toUpperCase()}` : 'Inspection')} • {todayStr}
              </Text>
            </View>
          </View>
          <ProfileAvatar size={36} />
        </View>

        <ScrollView
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Header Section */}
          <View style={styles.sectionHeaderBox}>
            <Text style={styles.sectionHeaderTitle}>Extracted Declarations Review</Text>
            <Text style={styles.sectionHeaderSubtitle}>
              Review and verify the data extracted via AI/OCR.
            </Text>
          </View>

          {loading ? (
            <ActivityIndicator size="large" color={colors.primary} style={{ marginVertical: 30 }} />
          ) : (
            <View style={styles.tableContainer}>
              {declarations.map((decl, idx) => {
                const label = FIELD_LABELS[decl.field_name] || FIELD_LABELS[decl.field_type] || (decl.field_name || decl.field_type || '').replace(/_/g, ' ');
                const isConflict = decl.ocr_confidence === 'CONFLICT' || decl.has_conflict || decl.extraction_status === 'CONFLICTING';
                const isOcrUnavailable = decl.extraction_status === 'OCR_UNAVAILABLE';
                const isNotFound = !isConflict && !isOcrUnavailable && (
                  (!decl.extracted_value && (!decl.effective_value || decl.effective_value === 'NOT_FOUND')) ||
                  decl.extraction_status === 'NOT_FOUND'
                );
                const isLast = idx === declarations.length - 1;

                return (
                  <View
                    key={decl.id || idx}
                    style={[
                      styles.tableRow,
                      isConflict && styles.rowConflict,
                      (isNotFound || isOcrUnavailable) && styles.rowNotFound,
                      !isLast && styles.rowBorder,
                    ]}
                  >
                    <View style={styles.rowTop}>
                      <Text
                        style={[
                          styles.fieldLabelCaps,
                          isConflict && styles.textRed,
                          (isNotFound || isOcrUnavailable) && styles.textAmber,
                        ]}
                      >
                        {label}
                      </Text>
                      <TouchableOpacity
                        style={styles.editBtn}
                        onPress={() => openEditModal(decl)}
                        activeOpacity={0.7}
                      >
                        <MaterialIcons name="edit" size={18} color={colors.primary} />
                      </TouchableOpacity>
                    </View>

                    {isConflict ? (
                      <View style={styles.conflictContent}>
                        <View style={styles.alertHeaderRow}>
                          <MaterialIcons name="warning" size={18} color={colors.statusRedText} />
                          <Text style={styles.conflictTitle}>CONFLICT DETECTED</Text>
                        </View>
                        <Text style={styles.conflictValues}>
                          {decl.effective_value || decl.extracted_value || 'Multiple values detected across panels'}
                        </Text>
                        <Text style={styles.conflictHelper}>
                          Two different values found across images. Manual verification required.
                        </Text>
                      </View>
                    ) : isOcrUnavailable ? (
                      <View style={styles.notFoundContent}>
                        <View style={styles.alertHeaderRow}>
                          <MaterialIcons name="info-outline" size={18} color={colors.statusAmberText} />
                          <Text style={styles.notFoundTitle}>OCR Unavailable</Text>
                        </View>
                        <Text style={styles.notFoundSubtext}>
                          OCR could not process this package view. Manual verification required.
                        </Text>
                        <TouchableOpacity
                          style={styles.manualEntryBtn}
                          onPress={() => openEditModal(decl)}
                          activeOpacity={0.7}
                        >
                          <Text style={styles.manualEntryText}>[ Enter Value Manually ]</Text>
                        </TouchableOpacity>
                      </View>
                    ) : isNotFound ? (
                      <View style={styles.notFoundContent}>
                        <View style={styles.alertHeaderRow}>
                          <MaterialIcons name="error" size={18} color={colors.statusAmberText} />
                          <Text style={styles.notFoundTitle}>Field Not Found on Package</Text>
                        </View>
                        <Text style={styles.notFoundSubtext}>OCR did not detect this field on the label.</Text>
                        <TouchableOpacity
                          style={styles.manualEntryBtn}
                          onPress={() => openEditModal(decl)}
                          activeOpacity={0.7}
                        >
                          <Text style={styles.manualEntryText}>[ Enter Value Manually ]</Text>
                        </TouchableOpacity>
                      </View>
                    ) : (
                      <View style={styles.valueRow}>
                        <Text style={styles.valueText}>
                          {decl.effective_value || decl.extracted_value || 'Not specified'}
                        </Text>
                      </View>
                    )}

                    {/* Chips Row */}
                    <View style={styles.chipsRow}>
                      <View style={styles.sourceChip}>
                        <MaterialIcons name="memory" size={14} color={colors.onSurfaceVariant} />
                        <Text style={styles.sourceChipText}>
                          {decl.verification_status === 'CORRECTED'
                            ? 'Inspector Corrected'
                            : isOcrUnavailable
                            ? 'Manual Verification Required'
                            : isNotFound
                            ? 'Pending Verification'
                            : 'AI/OCR Extracted'}
                        </Text>
                      </View>

                      {isConflict ? (
                        <View style={styles.conflictChip}>
                          <Text style={styles.conflictChipText}>CONFLICT — NEEDS MANUAL VERIFICATION</Text>
                        </View>
                      ) : isOcrUnavailable ? (
                        <View style={styles.notFoundChip}>
                          <Text style={styles.notFoundChipText}>OCR: unavailable</Text>
                        </View>
                      ) : isNotFound ? (
                        <View style={styles.notFoundChip}>
                          <Text style={styles.notFoundChipText}>OCR Result: not_found</Text>
                        </View>
                      ) : (
                        <View style={styles.goodChip}>
                          <Text style={styles.goodChipText}>
                            OCR Confidence: {decl.ocr_confidence || (decl.confidence ? `${Math.round(decl.confidence * 100)}%` : 'High')}
                          </Text>
                        </View>
                      )}
                    </View>

                    {/* Multi-Dimensional Indicators (PCR 2011 Rules 6, 7, 9, 12) */}
                    <View style={styles.dimensionChipsRow}>
                      {decl.readability_status ? (
                        <View style={[
                          styles.dimChip,
                          decl.readability_status === 'READABLE' ? styles.dimChipGreen : styles.dimChipAmber
                        ]}>
                          <MaterialIcons
                            name={decl.readability_status === 'READABLE' ? 'visibility' : 'visibility-off'}
                            size={12}
                            color={decl.readability_status === 'READABLE' ? colors.statusGreenText : colors.statusAmberText}
                          />
                          <Text style={[
                            styles.dimChipText,
                            decl.readability_status === 'READABLE' ? styles.dimTextGreen : styles.dimTextAmber
                          ]}>
                            {decl.readability_status.replace(/_/g, ' ')}
                          </Text>
                        </View>
                      ) : null}

                      {decl.placement_status ? (
                        <View style={[
                          styles.dimChip,
                          decl.placement_status === 'PLACEMENT_COMPLIANT'
                            ? styles.dimChipGreen
                            : decl.placement_status === 'PLACEMENT_NON_COMPLIANT'
                            ? styles.dimChipRed
                            : styles.dimChipAmber
                        ]}>
                          <MaterialIcons
                            name="crop-free"
                            size={12}
                            color={
                              decl.placement_status === 'PLACEMENT_COMPLIANT'
                                ? colors.statusGreenText
                                : decl.placement_status === 'PLACEMENT_NON_COMPLIANT'
                                ? colors.statusRedText
                                : colors.statusAmberText
                            }
                          />
                          <Text style={[
                            styles.dimChipText,
                            decl.placement_status === 'PLACEMENT_COMPLIANT'
                              ? styles.dimTextGreen
                              : decl.placement_status === 'PLACEMENT_NON_COMPLIANT'
                              ? styles.dimTextRed
                              : styles.dimTextAmber
                          ]}>
                            {decl.placement_status.replace('PLACEMENT_', '').replace(/_/g, ' ')}
                          </Text>
                        </View>
                      ) : null}

                      {decl.font_size_status ? (
                        <View style={[
                          styles.dimChip,
                          decl.font_size_status === 'FONT_SIZE_COMPLIANT'
                            ? styles.dimChipGreen
                            : decl.font_size_status === 'FONT_SIZE_NON_COMPLIANT'
                            ? styles.dimChipRed
                            : styles.dimChipNeutral
                        ]}>
                          <MaterialIcons
                            name="format-size"
                            size={12}
                            color={
                              decl.font_size_status === 'FONT_SIZE_COMPLIANT'
                                ? colors.statusGreenText
                                : decl.font_size_status === 'FONT_SIZE_NON_COMPLIANT'
                                ? colors.statusRedText
                                : colors.onSurfaceVariant
                            }
                          />
                          <Text style={[
                            styles.dimChipText,
                            decl.font_size_status === 'FONT_SIZE_COMPLIANT'
                              ? styles.dimTextGreen
                              : decl.font_size_status === 'FONT_SIZE_NON_COMPLIANT'
                              ? styles.dimTextRed
                              : styles.dimTextNeutral
                          ]}>
                            {decl.font_size_status.replace('FONT_SIZE_', '').replace(/_/g, ' ')}
                          </Text>
                        </View>
                      ) : null}

                      {decl.format_status ? (
                        <View style={[
                          styles.dimChip,
                          decl.format_status === 'COMPLIANT' ? styles.dimChipGreen : styles.dimChipAmber
                        ]}>
                          <MaterialIcons
                            name="rule"
                            size={12}
                            color={decl.format_status === 'COMPLIANT' ? colors.statusGreenText : colors.statusAmberText}
                          />
                          <Text style={[
                            styles.dimChipText,
                            decl.format_status === 'COMPLIANT' ? styles.dimTextGreen : styles.dimTextAmber
                          ]}>
                            Fmt: {decl.format_status.replace(/_/g, ' ')}
                          </Text>
                        </View>
                      ) : null}
                    </View>
                  </View>
                );
              })}
            </View>
          )}

          {/* Statutory Compliance Matrix Card (SIH PS 26034) */}
          {validationMatrix && validationMatrix.matrix && validationMatrix.matrix.length > 0 && (
            <View style={styles.matrixCard}>
              <TouchableOpacity
                style={styles.matrixCardHeader}
                onPress={() => setShowMatrixTable(!showMatrixTable)}
                activeOpacity={0.7}
              >
                <View style={styles.matrixHeaderLeft}>
                  <MaterialIcons name="verified-user" size={20} color={colors.primary} />
                  <View>
                    <Text style={styles.matrixCardTitle}>Declaration Compliance Matrix</Text>
                    <Text style={styles.matrixCardSubtitle}>
                      PCR 2011 Multi-dimensional Statutory Evaluation
                    </Text>
                  </View>
                </View>
                <MaterialIcons
                  name={showMatrixTable ? 'expand-less' : 'expand-more'}
                  size={24}
                  color={colors.primary}
                />
              </TouchableOpacity>

              {/* Summary Stats Badges */}
              {complianceSummary && (
                <View style={styles.matrixSummaryRow}>
                  <View style={styles.summaryPill}>
                    <Text style={styles.summaryPillLabel}>Detected</Text>
                    <Text style={styles.summaryPillVal}>
                      {complianceSummary.mandatory_declarations_detected}/7
                    </Text>
                  </View>
                  <View style={styles.summaryPill}>
                    <Text style={styles.summaryPillLabel}>Placement</Text>
                    <Text style={[styles.summaryPillVal, styles.textGreen]}>
                      {complianceSummary.placement_summary?.compliant || 0} OK
                    </Text>
                  </View>
                  <View style={styles.summaryPill}>
                    <Text style={styles.summaryPillLabel}>Readability</Text>
                    <Text style={[styles.summaryPillVal, styles.textGreen]}>
                      {complianceSummary.readability_summary?.good || 0} Good
                    </Text>
                  </View>
                  <View style={styles.summaryPill}>
                    <Text style={styles.summaryPillLabel}>Font Size</Text>
                    <Text style={[styles.summaryPillVal, styles.textNeutral]}>
                      {complianceSummary.font_size_summary?.undeterminable || 0} Undet
                    </Text>
                  </View>
                </View>
              )}

              {showMatrixTable && (
                <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.matrixTableScroll}>
                  <View style={styles.matrixTable}>
                    {/* Header Row */}
                    <View style={styles.matrixTableRowHeader}>
                      <Text style={[styles.matrixTh, { width: 110 }]}>Declaration</Text>
                      <Text style={[styles.matrixTh, { width: 55 }]}>Present</Text>
                      <Text style={[styles.matrixTh, { width: 75 }]}>Readable</Text>
                      <Text style={[styles.matrixTh, { width: 80 }]}>Placement</Text>
                      <Text style={[styles.matrixTh, { width: 80 }]}>Font Size</Text>
                      <Text style={[styles.matrixTh, { width: 75 }]}>Format</Text>
                      <Text style={[styles.matrixTh, { width: 95 }]}>Status</Text>
                    </View>

                    {/* Data Rows */}
                    {validationMatrix.matrix.map((row: any, rIdx: number) => {
                      const isRowComp = row.overall_status === 'COMPLIANT';
                      return (
                        <View key={rIdx} style={[styles.matrixTableRow, rIdx % 2 === 1 && styles.matrixTableRowAlt]}>
                          <Text style={[styles.matrixTdBold, { width: 110 }]} numberOfLines={1}>
                            {FIELD_LABELS[row.declaration] || row.declaration.replace(/_/g, ' ')}
                          </Text>
                          <Text style={[styles.matrixTd, { width: 55 }, row.present ? styles.textGreen : styles.textRed]}>
                            {row.present ? 'YES' : 'NO'}
                          </Text>
                          <Text style={[styles.matrixTd, { width: 75 }, row.readable === 'READABLE' ? styles.textGreen : styles.textAmber]} numberOfLines={1}>
                            {row.readable ? row.readable.replace(/_/g, ' ') : '—'}
                          </Text>
                          <Text style={[styles.matrixTd, { width: 80 }, row.placement === 'PLACEMENT_COMPLIANT' ? styles.textGreen : styles.textAmber]} numberOfLines={1}>
                            {row.placement ? row.placement.replace('PLACEMENT_', '').replace(/_/g, ' ') : '—'}
                          </Text>
                          <Text style={[styles.matrixTd, { width: 80 }, row.font_size === 'FONT_SIZE_COMPLIANT' ? styles.textGreen : styles.textNeutral]} numberOfLines={1}>
                            {row.font_size ? row.font_size.replace('FONT_SIZE_', '').replace(/_/g, ' ') : '—'}
                          </Text>
                          <Text style={[styles.matrixTd, { width: 75 }, row.format === 'COMPLIANT' ? styles.textGreen : styles.textAmber]} numberOfLines={1}>
                            {row.format ? row.format.replace(/_/g, ' ') : '—'}
                          </Text>
                          <Text style={[styles.matrixTdBold, { width: 95 }, isRowComp ? styles.textGreen : styles.textAmber]} numberOfLines={1}>
                            {isRowComp ? 'COMPLIANT' : 'MANUAL VERIF'}
                          </Text>
                        </View>
                      );
                    })}
                  </View>
                </ScrollView>
              )}
            </View>
          )}

          {/* Auxiliary Barcode & QR Code Evidence Card */}
          {barcodesSummary && (
            <View style={styles.barcodeCard}>
              <View style={styles.barcodeCardHeader}>
                <View style={[styles.barcodeHeaderLeft, isNarrowScreen && styles.barcodeHeaderLeftNarrow]}>
                  <MaterialIcons name="qr-code-2" size={22} color={colors.primary} style={styles.barcodeIcon} />
                  <Text style={styles.barcodeCardTitle}>Auxiliary Evidence: Barcode / QR</Text>
                </View>
                {barcodesSummary.detected ? (
                  <View style={[
                    styles.barcodeStatusBadge,
                    isNarrowScreen && styles.barcodeStatusBadgeNarrow,
                    barcodesSummary.has_conflict
                      ? styles.badgeRed
                      : barcodesSummary.items.some((i: any) => i.ocr_corroboration === 'CORROBORATING')
                      ? styles.badgeGreen
                      : barcodesSummary.items.some((i: any) => i.ocr_corroboration === 'EVIDENCE_CONFLICT')
                      ? styles.badgeAmber
                      : styles.badgeNeutral
                  ]}>
                    <Text style={[
                      styles.barcodeStatusText,
                      barcodesSummary.has_conflict
                        ? styles.textRed
                        : barcodesSummary.items.some((i: any) => i.ocr_corroboration === 'CORROBORATING')
                        ? styles.textGreen
                        : barcodesSummary.items.some((i: any) => i.ocr_corroboration === 'EVIDENCE_CONFLICT')
                        ? styles.textAmber
                        : styles.textNeutral
                    ]}>
                      {barcodesSummary.has_conflict
                        ? 'Multi-Panel Conflict'
                        : barcodesSummary.items.some((i: any) => i.ocr_corroboration === 'CORROBORATING')
                        ? 'Corroborated by OCR'
                        : barcodesSummary.items.some((i: any) => i.ocr_corroboration === 'EVIDENCE_CONFLICT')
                        ? 'OCR Discrepancy'
                        : 'Barcode Only'}
                    </Text>
                  </View>
                ) : (
                  <View style={[
                    styles.barcodeStatusBadge,
                    isNarrowScreen && styles.barcodeStatusBadgeNarrow,
                    styles.badgeNeutral
                  ]}>
                    <Text style={[styles.barcodeStatusText, styles.textNeutral]}>Not Detected</Text>
                  </View>
                )}
              </View>

              {barcodesSummary.detected ? (
                <View style={styles.barcodeBody}>
                  <View style={styles.barcodeDataRow}>
                    <Text style={styles.barcodeDataLabel}>Symbology:</Text>
                    <Text style={styles.barcodeDataValue}>{barcodesSummary.barcode_type || 'EAN-13'}</Text>
                  </View>
                  <View style={styles.barcodeDataRow}>
                    <Text style={styles.barcodeDataLabel}>Decoded Value:</Text>
                    <Text style={styles.barcodeDataValueCode} numberOfLines={3} ellipsizeMode="middle">
                      {barcodesSummary.consolidated_value || '—'}
                    </Text>
                  </View>
                  {barcodesSummary.items.length > 0 && barcodesSummary.items[0].bbox && (
                    <View style={styles.barcodeDataRow}>
                      <Text style={styles.barcodeDataLabel}>Coordinates:</Text>
                      <Text style={styles.barcodeDataSubtext} numberOfLines={2}>
                        [{barcodesSummary.items[0].bbox.join(', ')}]
                      </Text>
                    </View>
                  )}
                  {barcodesSummary.has_conflict && barcodesSummary.conflict_description && (
                    <Text style={styles.barcodeConflictText}>{barcodesSummary.conflict_description}</Text>
                  )}
                </View>
              ) : (
                <Text style={styles.barcodeEmptyText}>
                  No barcode or QR code was detected on the inspected package images.
                </Text>
              )}

              <View style={styles.barcodeDisclaimer}>
                <MaterialIcons name="info-outline" size={14} color={colors.onSurfaceVariant} style={styles.disclaimerIcon} />
                <Text style={styles.barcodeDisclaimerText}>
                  PCR 2011 Notice: Barcode presence serves as auxiliary identity evidence and does not substitute mandatory human-readable declarations.
                </Text>
              </View>
            </View>
          )}

          {/* Action Button: Compare with Online Listing (PS 26034) */}
          <TouchableOpacity
            style={styles.compareListingButton}
            onPress={() => navigation.navigate('ListingComparison', { inspectionId, inspectionNumber })}
            activeOpacity={0.85}
          >
            <View style={styles.btnInner}>
              <MaterialIcons name="language" size={18} color={colors.primary} />
              <Text style={styles.compareListingButtonText} numberOfLines={2}>Compare with Online Listing</Text>
            </View>
          </TouchableOpacity>

          {/* Action Button: Check for Potential Violations */}
          <TouchableOpacity
            style={styles.evaluateButton}
            onPress={handleEvaluateRules}
            disabled={evaluating}
            activeOpacity={0.85}
          >
            {evaluating ? (
              <ActivityIndicator size="small" color={colors.onPrimary} />
            ) : (
              <View style={styles.btnInner}>
                <MaterialIcons name="rule" size={20} color={colors.onPrimary} />
                <Text style={styles.evaluateButtonText} numberOfLines={2}>Check for Potential Violations</Text>
              </View>
            )}
          </TouchableOpacity>

          <View style={styles.footerNote}>
            <Text style={styles.footerNoteText}>Smart India Hackathon 2026 Prototype</Text>
          </View>
        </ScrollView>

        {/* Edit Modal */}
        <Modal visible={!!editingDecl} transparent animationType="fade">
          <View style={styles.modalOverlay}>
            <View style={styles.modalContent}>
              <View style={styles.modalHeader}>
                <Text style={typography.sectionHeader}>
                  Edit {editingDecl ? FIELD_LABELS[editingDecl.field_type] || editingDecl.field_type : 'Declaration'}
                </Text>
                <TouchableOpacity onPress={() => setEditingDecl(null)}>
                  <MaterialIcons name="close" size={22} color={colors.onSurfaceVariant} />
                </TouchableOpacity>
              </View>

              <View style={styles.modalBody}>
                <Text style={typography.labelCaps}>Corrected / Verified Value</Text>
                <TextInput
                  style={styles.modalInput}
                  value={correctedValue}
                  onChangeText={setCorrectedValue}
                  placeholder="Enter correct value from package"
                  placeholderTextColor={colors.outline}
                />

                <Text style={[typography.labelCaps, { marginTop: 12 }]}>Reason for Modification</Text>
                <TextInput
                  style={styles.modalInput}
                  value={correctionReason}
                  onChangeText={setCorrectionReason}
                  placeholder="e.g. Verified on physical package label"
                  placeholderTextColor={colors.outline}
                />
              </View>

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={styles.modalCancelBtn}
                  onPress={() => setEditingDecl(null)}
                  disabled={savingCorrection}
                >
                  <Text style={styles.modalCancelText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.modalSaveBtn}
                  onPress={handleSaveCorrection}
                  disabled={savingCorrection}
                  activeOpacity={0.85}
                >
                  {savingCorrection ? (
                    <ActivityIndicator size="small" color={colors.onPrimary} />
                  ) : (
                    <Text style={styles.modalSaveText}>Save Correction</Text>
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
    fontSize: 18,
    fontWeight: '700',
    color: colors.primary,
  },
  headerSubtitle: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
  },
  avatarCircle: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.surfaceContainerHigh,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarInitials: {
    ...typography.labelCaps,
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
  scrollContent: {
    paddingHorizontal: spacing.gutter,
    paddingTop: spacing.stackMd,
    paddingBottom: 90,
    gap: spacing.stackMd,
  },
  sectionHeaderBox: {
    gap: 2,
    marginBottom: 4,
  },
  sectionHeaderTitle: {
    ...typography.sectionHeader,
    fontSize: 16,
    lineHeight: 24,
    fontWeight: '600',
    color: colors.primary,
  },
  sectionHeaderSubtitle: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.onSurfaceVariant,
  },
  tableContainer: {
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    overflow: 'hidden',
  },
  tableRow: {
    padding: spacing.gutter,
    gap: 8,
  },
  rowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  rowConflict: {
    backgroundColor: colors.statusRedBg,
    borderColor: 'rgba(183, 28, 28, 0.2)',
  },
  rowNotFound: {
    backgroundColor: colors.statusAmberBg,
    borderColor: 'rgba(230, 81, 0, 0.2)',
  },
  rowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  fieldLabelCaps: {
    ...typography.labelCaps,
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 0.5,
    fontWeight: '600',
    color: colors.onSurfaceVariant,
    textTransform: 'uppercase',
  },
  textRed: {
    color: colors.statusRedText,
  },
  textAmber: {
    color: colors.statusAmberText,
  },
  editBtn: {
    padding: 4,
    borderRadius: borderRadius.DEFAULT,
  },
  valueRow: {
    marginBottom: 2,
  },
  valueText: {
    ...typography.bodyMd,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '600',
    color: colors.onSurface,
  },
  conflictContent: {
    gap: 4,
    marginBottom: 4,
  },
  alertHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  conflictTitle: {
    ...typography.bodyMd,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
    color: colors.statusRedText,
  },
  conflictValues: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.onSurface,
    marginLeft: 24,
  },
  conflictHelper: {
    ...typography.caption,
    fontSize: 12,
    color: colors.onSurfaceVariant,
    marginLeft: 24,
  },
  notFoundContent: {
    gap: 4,
    marginBottom: 4,
  },
  notFoundTitle: {
    ...typography.bodyMd,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
    color: colors.statusAmberText,
  },
  notFoundSubtext: {
    ...typography.bodySm,
    fontSize: 13,
    lineHeight: 18,
    color: colors.onSurface,
    marginLeft: 24,
  },
  manualEntryBtn: {
    marginLeft: 24,
    marginTop: 2,
  },
  manualEntryText: {
    ...typography.bodySm,
    fontSize: 13,
    fontWeight: '600',
    color: colors.primary,
    textDecorationLine: 'underline',
  },
  chipsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 8,
    marginTop: 2,
  },
  sourceChip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.DEFAULT,
    paddingHorizontal: 8,
    paddingVertical: 2,
    gap: 4,
  },
  sourceChipText: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
  },
  goodChip: {
    backgroundColor: colors.statusGreenBg,
    borderWidth: 1,
    borderColor: 'rgba(27, 94, 32, 0.2)',
    borderRadius: borderRadius.DEFAULT,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  goodChipText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.statusGreenText,
  },
  conflictChip: {
    backgroundColor: colors.statusRedBg,
    borderWidth: 1,
    borderColor: 'rgba(183, 28, 28, 0.2)',
    borderRadius: borderRadius.DEFAULT,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  conflictChipText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.statusRedText,
  },
  notFoundChip: {
    backgroundColor: colors.statusAmberBg,
    borderWidth: 1,
    borderColor: 'rgba(230, 81, 0, 0.2)',
    borderRadius: borderRadius.DEFAULT,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  notFoundChipText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '600',
    color: colors.statusAmberText,
  },
  compareListingButton: {
    backgroundColor: '#ffffff',
    borderWidth: 1.5,
    borderColor: colors.primary,
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: borderRadius.xl,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 8,
  },
  compareListingButtonText: {
    fontSize: 14,
    color: colors.primary,
    fontWeight: '600',
    textAlign: 'center',
    flexShrink: 1,
  },
  evaluateButton: {
    backgroundColor: colors.primary,
    paddingVertical: 14,
    paddingHorizontal: 16,
    borderRadius: borderRadius.xl,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 8,
  },
  btnInner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    flexShrink: 1,
  },
  evaluateButtonText: {
    ...typography.sectionHeader,
    fontSize: 15,
    lineHeight: 22,
    color: colors.onPrimary,
    fontWeight: '600',
    textAlign: 'center',
    flexShrink: 1,
  },
  footerNote: {
    alignItems: 'center',
    marginTop: 8,
    marginBottom: 8,
  },
  footerNoteText: {
    ...typography.caption,
    fontSize: 11,
    color: colors.onSurfaceVariant,
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
  modalBody: {
    gap: 6,
  },
  modalInput: {
    backgroundColor: colors.surfaceBright,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: borderRadius.lg,
    paddingHorizontal: 12,
    paddingVertical: 8,
    ...typography.bodyMd,
    color: colors.onSurface,
  },
  modalActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 8,
    marginTop: 8,
  },
  modalCancelBtn: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
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
  },
  modalSaveText: {
    ...typography.bodySm,
    fontWeight: '700',
    color: colors.onPrimary,
  },
  // Barcode & QR Code Card Styles
  barcodeCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    padding: spacing.gutter,
    marginTop: spacing.stackMd,
    marginBottom: spacing.stackSm,
  },
  barcodeCardHeader: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 8,
    marginBottom: spacing.tight,
  },
  barcodeHeaderLeft: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
  },
  barcodeHeaderLeftNarrow: {
    minWidth: '100%',
  },
  barcodeIcon: {
    marginTop: 1,
    flexShrink: 0,
  },
  barcodeCardTitle: {
    ...typography.bodyMd,
    fontWeight: '700',
    color: colors.primary,
    flex: 1,
    flexShrink: 1,
    lineHeight: 20,
  },
  barcodeStatusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    alignSelf: 'flex-start',
    maxWidth: '100%',
    flexShrink: 1,
  },
  barcodeStatusBadgeNarrow: {
    marginTop: 2,
  },
  barcodeStatusText: {
    ...typography.caption,
    fontWeight: '700',
    fontSize: 11,
    textAlign: 'center',
    flexShrink: 1,
  },
  badgeGreen: {
    backgroundColor: colors.statusGreenBg,
    borderColor: 'rgba(27, 94, 32, 0.25)',
  },
  badgeAmber: {
    backgroundColor: colors.statusAmberBg,
    borderColor: 'rgba(230, 81, 0, 0.25)',
  },
  badgeRed: {
    backgroundColor: colors.statusRedBg,
    borderColor: 'rgba(183, 28, 28, 0.25)',
  },
  badgeNeutral: {
    backgroundColor: colors.surfaceContainerLow,
    borderColor: colors.borderSubtle,
  },
  textGreen: {
    color: colors.statusGreenText,
  },
  textNeutral: {
    color: colors.onSurfaceVariant,
  },
  barcodeBody: {
    marginTop: spacing.tight,
    gap: 4,
  },
  barcodeDataRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
  },
  barcodeDataLabel: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.onSurfaceVariant,
    width: 95,
    flexShrink: 0,
    lineHeight: 18,
  },
  barcodeDataValue: {
    ...typography.bodySm,
    fontWeight: '600',
    color: colors.onSurface,
    flex: 1,
    flexShrink: 1,
    minWidth: 0,
  },
  barcodeDataValueCode: {
    ...typography.bodySm,
    fontWeight: '700',
    fontFamily: 'monospace',
    color: colors.primary,
    letterSpacing: 0.5,
    flex: 1,
    flexShrink: 1,
    minWidth: 0,
  },
  barcodeDataSubtext: {
    ...typography.caption,
    color: colors.onSurfaceVariant,
    fontSize: 11,
    flex: 1,
    flexShrink: 1,
    minWidth: 0,
    lineHeight: 16,
  },
  barcodeConflictText: {
    ...typography.caption,
    color: colors.statusRedText,
    fontWeight: '600',
    marginTop: 4,
    flexShrink: 1,
  },
  barcodeEmptyText: {
    ...typography.bodySm,
    color: colors.onSurfaceVariant,
    fontStyle: 'italic',
    marginTop: spacing.tight,
  },
  barcodeDisclaimer: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    marginTop: spacing.base,
    paddingTop: spacing.tight,
    borderTopWidth: 1,
    borderTopColor: colors.borderSubtle,
  },
  disclaimerIcon: {
    marginTop: 1,
    flexShrink: 0,
  },
  barcodeDisclaimerText: {
    ...typography.caption,
    fontSize: 10.5,
    color: colors.onSurfaceVariant,
    flex: 1,
    flexShrink: 1,
    minWidth: 0,
    lineHeight: 15,
  },
  // Dimension Chips (PCR 2011 Multi-Dimensional Compliance)
  dimensionChipsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 6,
  },
  dimChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 7,
    paddingVertical: 2.5,
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
  },
  dimChipGreen: {
    backgroundColor: colors.statusGreenBg,
    borderColor: 'rgba(27, 94, 32, 0.2)',
  },
  dimChipAmber: {
    backgroundColor: colors.statusAmberBg,
    borderColor: 'rgba(230, 81, 0, 0.2)',
  },
  dimChipRed: {
    backgroundColor: colors.statusRedBg,
    borderColor: 'rgba(183, 28, 28, 0.2)',
  },
  dimChipNeutral: {
    backgroundColor: colors.surfaceContainerLow,
    borderColor: colors.borderSubtle,
  },
  dimChipText: {
    ...typography.caption,
    fontSize: 10.5,
    fontWeight: '600',
  },
  dimTextGreen: {
    color: colors.statusGreenText,
  },
  dimTextAmber: {
    color: colors.statusAmberText,
  },
  dimTextRed: {
    color: colors.statusRedText,
  },
  dimTextNeutral: {
    color: colors.onSurfaceVariant,
  },
  // Compliance Matrix Card Styles (SIH PS 26034)
  matrixCard: {
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    padding: spacing.gutter,
    marginTop: spacing.stackMd,
    marginBottom: spacing.stackSm,
  },
  matrixCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  matrixHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  matrixCardTitle: {
    ...typography.bodyMd,
    fontWeight: '700',
    color: colors.primary,
  },
  matrixCardSubtitle: {
    ...typography.caption,
    color: colors.onSurfaceVariant,
    fontSize: 11,
  },
  matrixSummaryRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 10,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: colors.borderSubtle,
  },
  summaryPill: {
    flex: 1,
    minWidth: 65,
    backgroundColor: colors.surfaceContainerLow,
    paddingVertical: 5,
    paddingHorizontal: 8,
    borderRadius: borderRadius.DEFAULT,
    alignItems: 'center',
  },
  summaryPillLabel: {
    ...typography.caption,
    fontSize: 9.5,
    color: colors.onSurfaceVariant,
    textTransform: 'uppercase',
  },
  summaryPillVal: {
    ...typography.caption,
    fontWeight: '700',
    fontSize: 11.5,
    marginTop: 1,
    color: colors.onSurface,
  },
  matrixTableScroll: {
    marginTop: 10,
  },
  matrixTable: {
    borderRadius: borderRadius.DEFAULT,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    overflow: 'hidden',
  },
  matrixTableRowHeader: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceContainerLow,
    paddingVertical: 6,
    paddingHorizontal: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  matrixTh: {
    ...typography.caption,
    fontWeight: '700',
    fontSize: 10,
    color: colors.primary,
    textTransform: 'uppercase',
  },
  matrixTableRow: {
    flexDirection: 'row',
    paddingVertical: 6,
    paddingHorizontal: 8,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.04)',
    alignItems: 'center',
  },
  matrixTableRowAlt: {
    backgroundColor: 'rgba(0,0,0,0.015)',
  },
  matrixTd: {
    ...typography.caption,
    fontSize: 10.5,
    color: colors.onSurface,
  },
  matrixTdBold: {
    ...typography.caption,
    fontSize: 10.5,
    fontWeight: '700',
    color: colors.onSurface,
  },
});

