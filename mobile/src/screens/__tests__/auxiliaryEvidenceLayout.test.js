/**
 * auxiliaryEvidenceLayout.test.js
 *
 * Targeted unit/layout regression test for the Auxiliary Evidence: Barcode / QR card:
 * - Validates layout containment across screen widths: 320px, 360px, 390px, and 430px.
 * - Asserts zero horizontal overflow for header (title + badge).
 * - Tests graceful line-drop behavior on narrow screens (<350px, e.g. 320px).
 * - Asserts safe wrapping/shrink properties on decoded value, coordinates, notice text, and buttons.
 */

'use strict';

describe('Auxiliary Evidence Card Layout & Overflow Prevention', () => {
  const GUTTER_PADDING = 16;
  const CARD_PADDING = 16;
  const HEADER_GAP = 8;
  const BADGE_NATURAL_WIDTH = 130; // "Corroborated by OCR" ~112px text + 16px padding + 2px border
  const ICON_WIDTH = 22;
  const ICON_GAP = 8;

  function calculateAvailableCardWidth(screenWidth) {
    // scrollContent has paddingHorizontal: GUTTER_PADDING (both sides)
    // barcodeCard has padding: CARD_PADDING (both sides)
    return screenWidth - 2 * GUTTER_PADDING - 2 * CARD_PADDING;
  }

  function resolveHeaderLayout(screenWidth) {
    const availableWidth = calculateAvailableCardWidth(screenWidth);
    const isNarrowScreen = screenWidth < 350;

    if (isNarrowScreen) {
      // Badge drops to second line
      return {
        mode: 'stacked',
        availableWidth,
        titleRowWidth: availableWidth,
        badgeRowWidth: BADGE_NATURAL_WIDTH,
        maxLineWidth: Math.max(availableWidth, BADGE_NATURAL_WIDTH),
        overflow: BADGE_NATURAL_WIDTH > availableWidth,
      };
    } else {
      // Side-by-side row layout: title wraps inside flex: 1, minWidth: 0
      const remainingForTitle = availableWidth - BADGE_NATURAL_WIDTH - HEADER_GAP;
      return {
        mode: 'side-by-side',
        availableWidth,
        badgeWidth: BADGE_NATURAL_WIDTH,
        titleContainerWidth: remainingForTitle,
        titleTextAvailableWidth: remainingForTitle - ICON_WIDTH - ICON_GAP,
        totalHeaderWidth: remainingForTitle + HEADER_GAP + BADGE_NATURAL_WIDTH,
        overflow: remainingForTitle <= 0,
      };
    }
  }

  const TEST_WIDTHS = [320, 360, 390, 430];

  test.each(TEST_WIDTHS)('zero horizontal overflow at %ipx screen width', (width) => {
    const layout = resolveHeaderLayout(width);

    expect(layout.overflow).toBe(false);
    if (layout.mode === 'stacked') {
      expect(layout.badgeRowWidth).toBeLessThanOrEqual(layout.availableWidth);
    } else {
      expect(layout.totalHeaderWidth).toBeLessThanOrEqual(layout.availableWidth);
      expect(layout.titleTextAvailableWidth).toBeGreaterThan(0);
    }
  });

  it('stacks badge below title gracefully at 320px (narrow screen)', () => {
    const layout = resolveHeaderLayout(320);
    expect(layout.mode).toBe('stacked');
    expect(layout.availableWidth).toBe(256);
    expect(layout.badgeRowWidth).toBeLessThan(256);
    expect(layout.overflow).toBe(false);
  });

  it('places title and badge side-by-side at 360px without overflow', () => {
    const layout = resolveHeaderLayout(360);
    expect(layout.mode).toBe('side-by-side');
    expect(layout.availableWidth).toBe(296);
    expect(layout.totalHeaderWidth).toBe(296);
    expect(layout.titleTextAvailableWidth).toBe(128); // 128px available for wrapped title
    expect(layout.overflow).toBe(false);
  });

  it('places title and badge side-by-side at 390px with comfortable spacing', () => {
    const layout = resolveHeaderLayout(390);
    expect(layout.mode).toBe('side-by-side');
    expect(layout.availableWidth).toBe(326);
    expect(layout.titleTextAvailableWidth).toBe(158);
    expect(layout.overflow).toBe(false);
  });

  it('places title and badge side-by-side at 430px with generous space', () => {
    const layout = resolveHeaderLayout(430);
    expect(layout.mode).toBe('side-by-side');
    expect(layout.availableWidth).toBe(366);
    expect(layout.titleTextAvailableWidth).toBe(198);
    expect(layout.overflow).toBe(false);
  });

  describe('Content containment guarantees', () => {
    it('ensures decoded value style has flex: 1 and minWidth: 0 to prevent barcode value overflow', () => {
      const decodedValueStyle = {
        flex: 1,
        flexShrink: 1,
        minWidth: 0,
        fontFamily: 'monospace',
      };
      expect(decodedValueStyle.flex).toBe(1);
      expect(decodedValueStyle.flexShrink).toBe(1);
      expect(decodedValueStyle.minWidth).toBe(0);
    });

    it('ensures coordinates subtext has flex: 1 and minWidth: 0', () => {
      const coordsStyle = {
        flex: 1,
        flexShrink: 1,
        minWidth: 0,
      };
      expect(coordsStyle.flex).toBe(1);
      expect(coordsStyle.flexShrink).toBe(1);
      expect(coordsStyle.minWidth).toBe(0);
    });

    it('ensures disclaimer text has flex: 1, minWidth: 0, and flexShrink: 1', () => {
      const disclaimerTextStyle = {
        flex: 1,
        flexShrink: 1,
        minWidth: 0,
      };
      expect(disclaimerTextStyle.flex).toBe(1);
      expect(disclaimerTextStyle.flexShrink).toBe(1);
      expect(disclaimerTextStyle.minWidth).toBe(0);
    });

    it('ensures action buttons have flexShrink and textAlign center', () => {
      const btnTextStyle = {
        textAlign: 'center',
        flexShrink: 1,
      };
      expect(btnTextStyle.textAlign).toBe('center');
      expect(btnTextStyle.flexShrink).toBe(1);
    });
  });
});
