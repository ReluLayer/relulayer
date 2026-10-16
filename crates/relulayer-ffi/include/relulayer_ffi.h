#ifndef RELULAYER_FFI_H
#define RELULAYER_FFI_H

/* C-ABI opaque-handle interface for the ReluLayer v0.2.0-hardened boundary. */

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Opaque interceptor handle. The concrete layout is hidden from C callers. */
typedef struct ReluInterceptorOpaque ReluInterceptor;

/* Create an interceptor from a 32-byte boundary key.
 *
 * On success, returns 0 and writes a non-NULL handle to *out_handle.
 * On failure, returns a negative FFI error code and leaves *out_handle
 * unchanged. The caller must destroy the handle with
 * relulayer_interceptor_destroy.
 */
int32_t relulayer_interceptor_create(const uint8_t *key_ptr, size_t key_len,
                                     ReluInterceptor **out_handle);

/* Destroy an interceptor handle. Safe to call with NULL. */
void relulayer_interceptor_destroy(ReluInterceptor *handle);

/* Verify an action/payload against a replay-resistant receipt using a
 * persistent interceptor handle.
 *
 * expected_receipt_ptr must point to exactly 60 bytes.
 * out_receipt_ptr is optional; if non-NULL and verification succeeds, a copy
 * of the verified receipt is written to this 60-byte buffer.
 *
 * Returns 0 on success, or a negative FFI error code on failure.
 */
int32_t relulayer_intercept_and_authorize(
    ReluInterceptor *handle,
    const uint8_t *action_ptr, size_t action_len,
    const uint8_t *payload_ptr, size_t payload_len,
    const uint8_t *expected_receipt_ptr,
    uint8_t *out_receipt_ptr);

/* Stateless legacy verification helper.
 *
 * WARNING: This function intentionally lacks replay resistance. It creates a
 * fresh interceptor for every call, so monotonic counters and nonce windows
 * are not persisted. Use relulayer_interceptor_create /
 * relulayer_intercept_and_authorize for production replay resistance.
 */
int32_t relulayer_verify_stateless(
    const uint8_t *key_ptr, size_t key_len,
    const uint8_t *action_ptr, size_t action_len,
    const uint8_t *payload_ptr, size_t payload_len,
    const uint8_t *expected_receipt_ptr);

/* Issue a replay-resistant authorization receipt.
 *
 * Convenience function for the policy engine. nonce_ptr must point to 12 bytes.
 * The receipt is written to out_receipt_ptr (at least 60 bytes).
 */
int32_t relulayer_issue_receipt(
    const uint8_t *key_ptr, size_t key_len,
    const uint8_t *nonce_ptr,
    uint64_t timestamp,
    uint64_t counter,
    const uint8_t *action_ptr, size_t action_len,
    const uint8_t *payload_ptr, size_t payload_len,
    uint8_t *out_receipt_ptr);

#ifdef __cplusplus
}
#endif

#endif /* RELULAYER_FFI_H */
