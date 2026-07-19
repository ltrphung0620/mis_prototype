let fallbackSequence = 0;

/**
 * Create the idempotency key for one Founder-triggered evaluation cycle.
 *
 * The key is created once before the HTTP request. Callers must retain it while
 * retrying that request, then discard it after the server accepts the run.
 */
export function createRunRequestId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return `UI-${globalThis.crypto.randomUUID()}`;
  }

  fallbackSequence += 1;
  return `UI-${Date.now().toString(36)}-${fallbackSequence.toString(36)}`;
}
