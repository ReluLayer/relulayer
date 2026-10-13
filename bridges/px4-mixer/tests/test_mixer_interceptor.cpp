// SPDX-License-Identifier: Proprietary
// ReluLayer PX4 Mixer Interceptor Host Test Harness — Sprint 2

#include <array>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <random>
#include <vector>

#include "ReluLayerBarrier.hpp"

using relulayer::ReluLayerBarrier;

static constexpr std::size_t kFrames = 10000;
static constexpr float kSampleRateHz = 400.0f;
static constexpr float kUMin = 0.05f;
static constexpr float kUMax = 0.95f;

int main() {
  ReluLayerBarrier barrier{kUMin, kUMax};

  std::mt19937 rng(42);
  std::uniform_real_distribution<float> noise(-0.2f, 0.2f);
  std::bernoulli_distribution saturate(0.10);

  std::vector<double> frame_ns;
  frame_ns.reserve(kFrames);

  std::size_t violations = 0;
  std::size_t saturated_frames = 0;

  for (std::size_t frame = 0; frame < kFrames; ++frame) {
    std::array<float, ReluLayerBarrier::kNumMotors> raw{};

    // Quadrotor-like mixer mapping: roll, pitch, yaw, thrust.
    const float roll = std::sin(2.0f * 3.14159265f * 3.0f * frame / kSampleRateHz);
    const float pitch = std::cos(2.0f * 3.14159265f * 2.5f * frame / kSampleRateHz);
    const float yaw = (frame % 200 < 20) ? 0.9f : 0.0f;  // transient yaw kick
    const float thrust = 0.4f + 0.25f * std::sin(2.0f * 3.14159265f * 0.5f * frame / kSampleRateHz);

    raw[0] = thrust + roll + pitch + yaw + noise(rng);
    raw[1] = thrust - roll + pitch - yaw + noise(rng);
    raw[2] = thrust + roll - pitch - yaw + noise(rng);
    raw[3] = thrust - roll - pitch + yaw + noise(rng);

    // Inject deliberate saturated excursions every ~10 frames.
    if (saturate(rng)) {
      ++saturated_frames;
      const std::size_t victim = rng() % ReluLayerBarrier::kNumMotors;
      raw[victim] = 1.8f;  // allocator commanded beyond any physical ESC limit
    }

    // Also test extreme negative commands on a fixed motor.
    if (frame == kFrames / 2) {
      raw[0] = -0.5f;
      raw[1] = -10.0f;
    }

    auto t0 = std::chrono::high_resolution_clock::now();
    std::array<float, ReluLayerBarrier::kNumMotors> safe{};
    barrier.update(raw, safe);
    auto t1 = std::chrono::high_resolution_clock::now();

    const double ns = static_cast<double>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count());
    frame_ns.push_back(ns);

    for (std::size_t i = 0; i < ReluLayerBarrier::kNumMotors; ++i) {
      if (safe[i] < kUMin || safe[i] > kUMax) {
        std::cerr << "BOUND VIOLATION at frame " << frame << " motor " << i
                  << ": raw=" << raw[i] << " safe=" << safe[i] << '\n';
        ++violations;
      }
    }
  }

  double total_ns = 0.0;
  double max_ns = 0.0;
  for (double ns : frame_ns) {
    total_ns += ns;
    if (ns > max_ns) max_ns = ns;
  }
  const double avg_ns = total_ns / static_cast<double>(frame_ns.size());

  const auto& c = barrier.counters();

  std::cout << "\n=== ReluLayer PX4 Mixer Interceptor Host Test ===\n"
            << "Frames processed:      " << c.frames_processed << "\n"
            << "Saturated injections:    " << saturated_frames << "\n"
            << "Channels clipped:      " << c.channels_clipped << "\n"
            << "Invalid inputs:        " << c.invalid_inputs << "\n"
            << "Fallback pass-through: " << c.fallback_pass_through << "\n"
            << "Bound violations:      " << violations << "\n"
            << "Avg per-frame latency: " << avg_ns << " ns (" << avg_ns / 1000.0
            << " us)\n"
            << "Max per-frame latency: " << max_ns << " ns (" << max_ns / 1000.0
            << " us)\n"
            << "Target latency:        <1000 ns (<1.0 us)\n";

  if (violations != 0 || avg_ns >= 1000.0) {
    std::cerr << "\nTEST FAILED\n";
    return EXIT_FAILURE;
  }

  std::cout << "\nTEST PASSED\n";
  return EXIT_SUCCESS;
}
