// Scratch test to verify formatGeocodedAddress logic exactly matching NewInspectionScreen.tsx

const formatGeocodedAddress = (place) => {
  if (place.formattedAddress && typeof place.formattedAddress === 'string' && place.formattedAddress.trim()) {
    let cleaned = place.formattedAddress.trim();
    cleaned = cleaned.replace(/^[A-Z0-9]{4,8}\+[A-Z0-9]{2,}\s*,?\s*/i, '').trim();
    const isRawCoord =
      /^[-+]?([1-8]?\d(\.\d+)?|90(\.0+)?),\s*[-+]?(180(\.0+)?|((1[0-7]\d)|([1-9]?\d))(\.\d+)?)$/.test(cleaned) ||
      /^[0-9+.,\s-]+(N|S|E|W)?$/i.test(cleaned);
    if (cleaned && !isRawCoord && /[a-zA-Z]/.test(cleaned)) {
      return cleaned;
    }
  }

  const candidateParts = [];

  const addPart = (part) => {
    if (!part || typeof part !== 'string') return;
    const trimmed = part.trim();
    if (!trimmed) return;
    const lower = trimmed.toLowerCase();
    if (['null', 'undefined', 'unnamed road', 'unknown location', 'unnamed'].includes(lower)) return;
    const isCodeOrCoord =
      /^[0-9+.,\s-]+(N|S|E|W)?$/i.test(trimmed) ||
      /^[A-Z0-9]{4,8}\+[A-Z0-9]{2,}/.test(trimmed) ||
      /^[-+]?([1-8]?\d(\.\d+)?|90(\.0+)?),\s*[-+]?(180(\.0+)?|((1[0-7]\d)|([1-9]?\d))(\.\d+)?)$/.test(trimmed);
    if (isCodeOrCoord) return;
    if (!candidateParts.some((p) => p.toLowerCase() === lower)) {
      candidateParts.push(trimmed);
    }
  };

  addPart(place.name);

  const streetComponents = [place.streetNumber, place.street]
    .filter((s) => typeof s === 'string' && s.trim().length > 0)
    .map((s) => s.trim());
  const combinedStreet = streetComponents.join(' ').trim();
  if (combinedStreet) {
    addPart(combinedStreet);
  }

  addPart(place.district);
  addPart(place.subregion);
  addPart(place.city);
  addPart(place.region);

  if (candidateParts.length > 0 && place.postalCode && typeof place.postalCode === 'string' && place.postalCode.trim()) {
    addPart(place.postalCode);
  }

  addPart(place.country);

  return candidateParts.join(', ').trim();
};

const assert = require('assert');

// Test 1: Azadpur, Delhi, India
const res1 = formatGeocodedAddress({
  district: 'Azadpur',
  region: 'Delhi',
  country: 'India',
});
console.log('Test 1:', res1);
assert.strictEqual(res1, 'Azadpur, Delhi, India');

// Test 2: Sector/Street, City, Region, Country
const res2 = formatGeocodedAddress({
  street: 'Sector 4',
  city: 'Gurugram',
  region: 'Haryana',
  country: 'India',
});
console.log('Test 2:', res2);
assert.strictEqual(res2, 'Sector 4, Gurugram, Haryana, India');

// Test 3: Place with plus-code prefix in formattedAddress
const res3 = formatGeocodedAddress({
  formattedAddress: '7JWV+XX Azadpur Sabzi Mandi, Delhi, India',
});
console.log('Test 3:', res3);
assert.strictEqual(res3, 'Azadpur Sabzi Mandi, Delhi, India');

// Test 4: Pure coords in formattedAddress rejected, fallback to parts
const res4 = formatGeocodedAddress({
  formattedAddress: '28.7041, 77.1025',
  district: 'Karol Bagh',
  city: 'New Delhi',
  country: 'India',
});
console.log('Test 4:', res4);
assert.strictEqual(res4, 'Karol Bagh, New Delhi, India');

// Test 5: Empty fields returns empty string
const res5 = formatGeocodedAddress({});
console.log('Test 5:', `"${res5}"`);
assert.strictEqual(res5, '');

// Test 6: Deduplication (city === region)
const res6 = formatGeocodedAddress({
  district: 'Connaught Place',
  city: 'Delhi',
  region: 'Delhi',
  country: 'India',
});
console.log('Test 6:', res6);
assert.strictEqual(res6, 'Connaught Place, Delhi, India');

// Test 7: Street number + street name combined
const res7 = formatGeocodedAddress({
  streetNumber: '12',
  street: 'Main Market Road',
  district: 'Lajpat Nagar',
  city: 'New Delhi',
  postalCode: '110024',
  country: 'India',
});
console.log('Test 7:', res7);
assert.strictEqual(res7, '12 Main Market Road, Lajpat Nagar, New Delhi, India');

console.log('\nAll 7 formatGeocodedAddress tests passed successfully!');
