// SPDX-License-Identifier: Proprietary
// ReluLayer PX4 Mixer Barrier — Sprint 2

#include "ReluLayerBarrier.hpp"

#include <cmath>
#include <cstddef>

namespace relulayer {

ReluLayerBarrier::ReluLayerBarrier() {
  // Upper-bound constraint: u <= u_max via a[0]*u <= b[0].
  constraints_.a[0] = 1.0f;
  constraints_.b[0] = kDefaultUMax;

  // Leave remaining constraints wide-open.
  for (std::size_t i = 1; i < 4; ++i) {
    constraints_.a[i] = 0.0f;
    constraints_.b[i] = std::numeric_limits<float>::max();
  }
}

ReluLayerBarrier::ReluLayerBarrier(float u_min, float u_max)
    : ReluLayerBarrier() {
  limits_.u_min = u_min;
  limits_.u_max = u_max;
  constraints_.b[0] = u_max;
}

bool ReluLayerBarrier::isFinite(float value) noexcept {
#if defined(__PX4_NUTTX)
  // NuttX has full C++17 support; __builtin_isfinite is safe and small.
  return __builtin_isfinite(value);
#else
  return std::isfinite(value);
#endif
}

float ReluLayerBarrier::hardClamp(float value, float lo, float hi) noexcept {
  if (value < lo) return lo;
  if (value > hi) return hi;
  return value;
}

float ReluLayerBarrier::solveChannel(float raw) const {
  SolverResult result{};
  result.status = SolverStatus_InvalidInput;

  const int32_t rc =
      relulayer_solve_active_set(raw, limits_, &constraints_, &result);

  if (rc != 0 || result.status != SolverStatus_Optimal) {
    ++counters_.invalid_inputs;
    // Fallback: hard-clamp raw command rather than propagating an unsafe value.
    ++counters_.fallback_pass_through;
    return hardClamp(raw, limits_.u_min, limits_.u_max);
  }

  const float bounded = hardClamp(result.u_safe, limits_.u_min, limits_.u_max);

  if (bounded != raw) {
    ++counters_.channels_clipped;
  }

  return bounded;
}

bool ReluLayerBarrier::update(const std::array<float, kNumMotors>& raw,
                              std::array<float, kNumMotors>& safe) {
  bool all_optimal = true;

  for (std::size_t i = 0; i < kNumMotors; ++i) {
    if (!isFinite(raw[i])) {
      ++counters_.invalid_inputs;
      ++counters_.fallback_pass_through;
      safe[i] = limits_.u_min;  // Idle to prevent flameout.
      all_optimal = false;
      continue;
    }

    safe[i] = solveChannel(raw[i]);
    if (counters_.fallback_pass_through > 0) {
      // Per-call fallback tracking already incremented; mark frame.
      all_optimal = false;
    }
  }

  ++counters_.frames_processed;
  return all_optimal;
}

}  // namespace relulayer
