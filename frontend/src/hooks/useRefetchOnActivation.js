import { useEffect } from 'react';

/**
 * TECH-39: refetch-on-activation primitive (blueprint §2).
 *
 * useRefetchOnActivation(active, fn) — whenever `active` becomes truthy,
 * call `fn()`; hidden tabs never fetch. Thin wrapper over a single effect
 * with deps [active, fn]:
 * - mount with active=true runs the effect once → fn() once;
 * - flipping active false→true calls fn();
 * - active→active re-renders do NOT refetch while fn's identity is stable.
 *
 * Contract: fn MUST be stable (call sites pass a useCallback or a
 * hook-returned stable function). If fn changes identity while active is
 * true, the effect re-runs and calls fn again — the call site controls
 * refetch frequency through fn's identity.
 */
export function useRefetchOnActivation(active, fn) {
  useEffect(() => {
    if (active) fn();
  }, [active, fn]);
}
