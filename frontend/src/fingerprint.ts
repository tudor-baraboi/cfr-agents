/**
 * FingerprintJS visitor identification utility.
 * 
 * Uses FingerprintJS open source library to generate a unique
 * visitor ID for rate limiting purposes.
 */

import FingerprintJS from '@fingerprintjs/fingerprintjs';
import { branding } from './config';

// Cache key for storing visitor ID
const VISITOR_ID_KEY = `${branding.sessionStoragePrefix}-visitor-id`;

// Singleton promise for the FingerprintJS agent
let fpPromise: Promise<any> | null = null;

/**
 * Initialize the FingerprintJS agent (lazy initialization).
 */
function getAgent(): Promise<any> {
  if (!fpPromise) {
    fpPromise = FingerprintJS.load();
  }
  return fpPromise;
}

/**
 * Get the visitor ID, using cached value if available.
 * 
 * The visitor ID is cached in sessionStorage to avoid
 * regenerating it on every page load (which could produce
 * slightly different values).
 * 
 * @returns Promise resolving to the visitor ID string
 */
export async function getVisitorId(): Promise<string> {
  // Check cache first
  const cached = sessionStorage.getItem(VISITOR_ID_KEY);
  if (cached) {
    return cached;
  }

  // Generate new visitor ID
  try {
    const fp = await getAgent();
    const result = await fp.get();
    const visitorId = result.visitorId;
    
    // Cache for this session
    sessionStorage.setItem(VISITOR_ID_KEY, visitorId);
    
    return visitorId;
  } catch (error) {
    console.error('Failed to get visitor ID:', error);
    // Fall back to a random ID if fingerprinting fails
    const fallbackId = `fallback-${Math.random().toString(36).substring(2, 15)}`;
    sessionStorage.setItem(VISITOR_ID_KEY, fallbackId);
    return fallbackId;
  }
}

/**
 * Clear the cached visitor ID.
 * Useful for testing or when user wants to reset their session.
 */
export function clearVisitorId(): void {
  sessionStorage.removeItem(VISITOR_ID_KEY);
  fpPromise = null;
}
