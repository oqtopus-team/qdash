// Robust qubit ID sorting utilities

/**
 * Natural sorting function for qubit IDs
 * Handles cases like: Q1, Q2, Q10, Q1_2, Q10_1, etc.
 */
export function naturalSortQIDs(a: string, b: string): number {
  // Split into parts: alphanumeric segments
  const aParts = a.match(/(\d+|\D+)/g) || [a];
  const bParts = b.match(/(\d+|\D+)/g) || [b];

  const maxLength = Math.max(aParts.length, bParts.length);

  for (let i = 0; i < maxLength; i++) {
    const aPart = aParts[i] || "";
    const bPart = bParts[i] || "";

    // If both parts are numeric, compare as numbers
    const aNum = parseInt(aPart, 10);
    const bNum = parseInt(bPart, 10);

    if (!isNaN(aNum) && !isNaN(bNum)) {
      if (aNum !== bNum) {
        return aNum - bNum;
      }
    } else {
      // Compare as strings
      const comparison = aPart.localeCompare(bPart);
      if (comparison !== 0) {
        return comparison;
      }
    }
  }

  return 0;
}

/**
 * Extract numeric ID from qubit string for simple cases
 * Returns null if no clear numeric pattern is found
 */
export function extractQubitNumber(qid: string): number | null {
  // Try to find the first number in the string
  const match = qid.match(/\d+/);
  if (match) {
    return parseInt(match[0], 10);
  }
  return null;
}

/**
 * Validate if a string looks like a valid qubit ID
 */
export function isValidQubitID(qid: string): boolean {
  // Basic validation: should contain at least one letter and one number
  return /[a-zA-Z]/.test(qid) && /\d/.test(qid);
}

/**
 * Format qubit ID for display (ensure consistent formatting)
 */
export function formatQubitID(qid: string): string {
  return qid.trim().toUpperCase();
}

/**
 * Sort an array of objects by their qid property
 */
export function sortByQubitID<T extends { qid: string }>(items: T[]): T[] {
  return [...items].sort((a, b) => naturalSortQIDs(a.qid, b.qid));
}

// Examples of expected sorting behavior:
// ['Q1', 'Q2', 'Q10', 'Q20'] -> ['Q1', 'Q2', 'Q10', 'Q20']
// ['Q1_1', 'Q1_2', 'Q1_10'] -> ['Q1_1', 'Q1_2', 'Q1_10']
// ['q1', 'Q2', 'q10'] -> ['Q1', 'Q2', 'Q10'] (after formatting)
