// SPDX-License-Identifier: Proprietary
// ReluLayer PX4 Mixer Barrier — Sprint 2
// Drop-in safety governor between the PX4 control allocator and ESC outputs.

#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

extern "C" {
#include "relulayer.h"
}

namespace relulayer {

/**
 * Standalone C++17 PX4-style interceptor for quadrotor motor demands.
 *
 * Subscribes to a raw actuator_motors-like array, routes each channel
 * through the relulayer active-set C-ABI governor, and produces a safe
 * actuator_motors_safe array bounded to [u_min, u_max].
 */
class ReluLayerBarrier {
 public:
  static constexpr std::size_t kNumMotors = 4;

  static constexpr float kDefaultUMin = 0.05f;
  static constexpr float kDefaultUMax = 0.95f;

  struct Counters {
    std::uint64_t frames_processed{0};
    std::uint64_t channels_clipped{0};
    std::uint64_t invalid_inputs{0};
    std::uint64_t fallback_pass_through{0};
  };

  ReluLayerBarrier();
  explicit ReluLayerBarrier(float u_min, float u_max);

  /**
   * Run one 400 Hz mixer frame through the safety barrier.
   *
   * @param raw  Normalized motor demands from the allocator (length kNumMotors).
   * @param safe Bounded ESC commands to publish (length kNumMotors).
   * @return true if all channels solved optimally, false if any fallback path was used.
   */
  bool update(const std::array<float, kNumMotors>& raw,
              std::array<float, kNumMotors>& safe);

  /**
   * Run one channel through the active-set solver and hard-limit the result.
   */
  float solveChannel(float raw) const;

  [[nodiscard]] const Counters& counters() const noexcept { return counters_; }
  [[nodiscard]] float u_min() const noexcept { return limits_.u_min; }
  [[nodiscard]] float u_max() const noexcept { return limits_.u_max; }

 private:
  ActuatorLimits limits_{kDefaultUMin, kDefaultUMax};
  LinearConstraints constraints_{};
  mutable Counters counters_{};

  static bool isFinite(float value) noexcept;
  static float hardClamp(float value, float lo, float hi) noexcept;
};

}  // namespace relulayer
