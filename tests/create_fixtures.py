import cv2
import numpy as np
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURES_DIR.mkdir(exist_ok=True)

def generate_test_fixtures():
    # 1. Good Clear Package Image with All 7 Declarations
    clear_img = np.ones((800, 800, 3), dtype=np.uint8) * 220
    cv2.rectangle(clear_img, (40, 40), (760, 760), (30, 30, 30), 4)
    cv2.putText(clear_img, "PREMIUM BASMATI RICE", (80, 130), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (10, 10, 10), 3)
    cv2.putText(clear_img, "NET QUANTITY: 5 kg", (80, 220), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (10, 10, 10), 2)
    cv2.putText(clear_img, "MRP Rs. 450.00 (INCL. OF ALL TAXES)", (80, 310), cv2.FONT_HERSHEY_SIMPLEX, 0.95, (10, 10, 10), 2)
    cv2.putText(clear_img, "MFD: 08/2026", (80, 400), cv2.FONT_HERSHEY_SIMPLEX, 0.95, (10, 10, 10), 2)
    cv2.putText(clear_img, "MFG BY: AGRO FOODS PVT LTD, GORAKHPUR UP", (80, 490), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (10, 10, 10), 2)
    cv2.putText(clear_img, "CUSTOMER CARE: 1800-11-2233 / CARE@AGRO.IN", (80, 580), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (10, 10, 10), 2)
    cv2.putText(clear_img, "COUNTRY OF ORIGIN: INDIA", (80, 680), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (10, 10, 10), 2)
    cv2.imwrite(str(FIXTURES_DIR / "good_package.jpg"), clear_img)
    cv2.imwrite(str(FIXTURES_DIR / "clear_package.jpg"), clear_img)

    # 2. Package with Missing Declarations (Missing Net Qty, Mfg Date, Customer Care)
    missing_img = np.ones((800, 800, 3), dtype=np.uint8) * 220
    cv2.rectangle(missing_img, (40, 40), (760, 760), (30, 30, 30), 4)
    cv2.putText(missing_img, "ORGANIC WHEAT FLOUR", (80, 180), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (10, 10, 10), 3)
    cv2.putText(missing_img, "MRP Rs. 280.00", (80, 340), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (10, 10, 10), 2)
    cv2.putText(missing_img, "MFG BY: NATURAL FARMS INDIA", (80, 500), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (10, 10, 10), 2)
    cv2.imwrite(str(FIXTURES_DIR / "missing_declarations_package.jpg"), missing_img)

    # 3. Multi-Panel Back Label Image
    back_img = np.ones((800, 800, 3), dtype=np.uint8) * 230
    cv2.rectangle(back_img, (40, 40), (760, 760), (40, 40, 40), 3)
    cv2.putText(back_img, "NUTRITIONAL FACTS & DETAILS", (80, 140), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (20, 20, 20), 2)
    cv2.putText(back_img, "PACKED BY: GREEN MILLS PVT LTD", (80, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 20), 2)
    cv2.putText(back_img, "NET CONTENT: 1000 g", (80, 360), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (20, 20, 20), 2)
    cv2.putText(back_img, "MAX RETAIL PRICE: Rs. 120.00 (INCL. TAXES)", (80, 470), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 20), 2)
    cv2.putText(back_img, "FOR COMPLAINTS: 1800-44-5566 / HELP@GREENMILLS.COM", (80, 580), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (20, 20, 20), 2)
    cv2.putText(back_img, "BATCH: GM-2026-X1", (80, 690), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
    cv2.imwrite(str(FIXTURES_DIR / "multi_panel_back.jpg"), back_img)

    # 4. Imported Product Scenario (Evenly Spaced 7 Lines)
    imported_img = np.ones((800, 800, 3), dtype=np.uint8) * 225
    cv2.rectangle(imported_img, (40, 40), (760, 760), (30, 30, 30), 4)
    cv2.putText(imported_img, "EXTRA VIRGIN OLIVE OIL", (80, 130), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (10, 10, 10), 3)
    cv2.putText(imported_img, "NET VOLUME: 1 L", (80, 220), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (10, 10, 10), 2)
    cv2.putText(imported_img, "MRP Rs. 1450.00 (INCL. OF ALL TAXES)", (80, 310), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (10, 10, 10), 2)
    cv2.putText(imported_img, "IMPORTED & PACKED BY: MEDITERRANEAN IMPORTS DELHI", (80, 400), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (10, 10, 10), 2)
    cv2.putText(imported_img, "MFD / IMPORT DATE: 04/2026", (80, 490), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (10, 10, 10), 2)
    cv2.putText(imported_img, "CONSUMER CARE: 1800-77-8899 / CARE@MEDIMPORTS.IN", (80, 580), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (10, 10, 10), 2)
    cv2.putText(imported_img, "COUNTRY OF ORIGIN: SPAIN", (80, 680), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (10, 10, 10), 2)
    cv2.imwrite(str(FIXTURES_DIR / "imported_product_package.jpg"), imported_img)

    # 5. Blurry Package Image
    blurry_img = cv2.GaussianBlur(clear_img, (35, 35), 0)
    cv2.imwrite(str(FIXTURES_DIR / "blurry_package.jpg"), blurry_img)

    # 6. Low Quality / Dark Image
    dark_img = (clear_img.astype(np.float32) * 0.08).astype(np.uint8)
    cv2.imwrite(str(FIXTURES_DIR / "dark_package.jpg"), dark_img)

    # 7. Low Resolution Image
    low_res_img = cv2.resize(clear_img, (200, 200))
    cv2.imwrite(str(FIXTURES_DIR / "low_res_package.jpg"), low_res_img)

    print(f"Generated realistic test fixtures in {FIXTURES_DIR}")

if __name__ == "__main__":
    generate_test_fixtures()
