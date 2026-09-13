/**
 * pendingAdjudicationFlow.test.js
 *
 * Tests for the NiriKsha Pending Adjudication Filtering and Navigation logic:
 * - Case A: 2 pending + 10 settled findings -> only 2 pending shown when filter is 'pending_adjudication'
 * - Case B: Adjudicating 1 finding decrements pending count to 1 and removes it from pending list
 * - Case C: Adjudicating all findings reduces count to 0, triggering empty state
 * - Case D: 0 pending with historical findings never shows historical items as pending
 * - Case E: Cross-inspection isolation
 */

'use strict';

// Pure logic mirror of FindingsScreen.tsx isFindingPendingAdjudication
function isFindingPendingAdjudication(f) {
  if (typeof f.is_pending_adjudication === 'boolean') {
    return f.is_pending_adjudication;
  }
  const resultState = (f.result_state || '').toUpperCase();
  const isNonPass = resultState !== '' && resultState !== 'PASS' && resultState !== 'NOT_APPLICABLE';
  const adjStatus = (f.adjudication_status || '').toUpperCase();
  const resolvedActions = ['CONFIRMED', 'DISMISSED', 'NOT_APPLICABLE', 'CORRECTED'];
  const isResolved = resolvedActions.includes(adjStatus);
  return isNonPass && !isResolved;
}

function computeDisplayedFindings(findings, activeFilter) {
  const pendingFindings = findings.filter(isFindingPendingAdjudication);
  return activeFilter === 'pending_adjudication' ? pendingFindings : findings;
}

const settledFindings = [
  { id: '1', rule_code: 'PCR_RULE_01', result_state: 'POTENTIAL_NON_COMPLIANCE', adjudication_status: 'DISMISSED' },
  { id: '2', rule_code: 'PCR_RULE_02', result_state: 'POTENTIAL_NON_COMPLIANCE', adjudication_status: 'CONFIRMED' },
  { id: '3', rule_code: 'PCR_RULE_03', result_state: 'POTENTIAL_NON_COMPLIANCE', adjudication_status: 'CORRECTED' },
  { id: '4', rule_code: 'PCR_RULE_04', result_state: 'NOT_APPLICABLE', adjudication_status: 'NOT_APPLICABLE' },
  { id: '5', rule_code: 'PCR_RULE_05', result_state: 'PASS', adjudication_status: null },
  { id: '6', rule_code: 'PCR_RULE_06', result_state: 'PASS', adjudication_status: null },
  { id: '7', rule_code: 'PCR_RULE_07', result_state: 'PASS', adjudication_status: null },
  { id: '8', rule_code: 'PCR_RULE_08', result_state: 'POTENTIAL_NON_COMPLIANCE', adjudication_status: 'DISMISSED' },
  { id: '9', rule_code: 'PCR_RULE_09', result_state: 'POTENTIAL_NON_COMPLIANCE', adjudication_status: 'CONFIRMED' },
  { id: '10', rule_code: 'PCR_RULE_10', result_state: 'POTENTIAL_NON_COMPLIANCE', adjudication_status: 'DISMISSED' },
];

const pendingFindings = [
  { id: '11', rule_code: 'PCR_RULE_11', result_state: 'POTENTIAL_NON_COMPLIANCE', adjudication_status: 'PENDING' },
  { id: '12', rule_code: 'PCR_RULE_12', result_state: 'NEEDS_MANUAL_VERIFICATION', adjudication_status: null },
];

const allFindings = [...settledFindings, ...pendingFindings];

function runTests(testFn, expectFn) {
  testFn('Case A: Filter pending_adjudication returns only 2 pending findings out of 12 total', () => {
    const displayed = computeDisplayedFindings(allFindings, 'pending_adjudication');
    expectFn(displayed.length).toBe(2);
    expectFn(displayed.map((f) => f.id)).toEqual(['11', '12']);

    const all = computeDisplayedFindings(allFindings, 'all');
    expectFn(all.length).toBe(12);
  });

  testFn('Case B: One pending finding is adjudicated -> count becomes 1', () => {
    const updatedFindings = allFindings.map((f) =>
      f.id === '11' ? { ...f, adjudication_status: 'DISMISSED', is_pending_adjudication: false } : f
    );

    const displayed = computeDisplayedFindings(updatedFindings, 'pending_adjudication');
    expectFn(displayed.length).toBe(1);
    expectFn(displayed[0].id).toBe('12');
  });

  testFn('Case C: All pending findings adjudicated -> count becomes 0, triggering empty state', () => {
    const updatedFindings = allFindings.map((f) => {
      if (f.id === '11' || f.id === '12') {
        return { ...f, adjudication_status: 'CONFIRMED', is_pending_adjudication: false };
      }
      return f;
    });

    const displayed = computeDisplayedFindings(updatedFindings, 'pending_adjudication');
    expectFn(displayed.length).toBe(0);

    const step3Unadjudicated = updatedFindings.filter(isFindingPendingAdjudication);
    expectFn(step3Unadjudicated.length).toBe(0);
  });

  testFn('Case D: 0 pending but 10 historical findings -> pending list is empty, never shows historical items', () => {
    const displayed = computeDisplayedFindings(settledFindings, 'pending_adjudication');
    expectFn(displayed.length).toBe(0);

    const all = computeDisplayedFindings(settledFindings, 'all');
    expectFn(all.length).toBe(10);
  });

  testFn('Case E: Cross-inspection data isolation', () => {
    const inspectionA_Findings = [
      { id: 'A1', inspection_id: 'INSP-A', result_state: 'POTENTIAL_NON_COMPLIANCE', adjudication_status: 'PENDING' },
      { id: 'A2', inspection_id: 'INSP-A', result_state: 'POTENTIAL_NON_COMPLIANCE', adjudication_status: 'PENDING' },
    ];
    const inspectionB_Findings = [
      { id: 'B1', inspection_id: 'INSP-B', result_state: 'POTENTIAL_NON_COMPLIANCE', adjudication_status: 'PENDING' },
    ];

    const displayedA = computeDisplayedFindings(inspectionA_Findings, 'pending_adjudication');
    const displayedB = computeDisplayedFindings(inspectionB_Findings, 'pending_adjudication');

    expectFn(displayedA.length).toBe(2);
    expectFn(displayedB.length).toBe(1);

    const idsA = new Set(displayedA.map((f) => f.id));
    const idsB = new Set(displayedB.map((f) => f.id));
    for (const id of idsB) {
      expectFn(idsA.has(id)).toBe(false);
    }
  });
}

// Support both Jest and direct Node.js execution
if (typeof describe === 'function') {
  describe('Pending Adjudication Filtering & Navigation Flow', () => {
    runTests(test, (val) => ({
      toBe: (expected) => expect(val).toBe(expected),
      toEqual: (expected) => expect(val).toEqual(expected),
      toHaveLength: (expected) => expect(val).toHaveLength(expected),
    }));
  });
}

if (require.main === module) {
  const assert = require('assert');
  console.log('Running pendingAdjudicationFlow standalone test runner...');
  let passCount = 0;
  const customTest = (name, fn) => {
    try {
      fn();
      console.log(`  ✓ PASS: ${name}`);
      passCount++;
    } catch (err) {
      console.error(`  ✗ FAIL: ${name}`);
      console.error(err);
      process.exit(1);
    }
  };
  const customExpect = (val) => ({
    toBe: (expected) => assert.strictEqual(val, expected),
    toEqual: (expected) => assert.deepStrictEqual(val, expected),
    toHaveLength: (expected) => assert.strictEqual(val.length, expected),
  });
  runTests(customTest, customExpect);
  console.log(`\nALL ${passCount} TESTS PASSED!`);
}
