/*
 * ReluLayer C HIL Driver Harness
 * US Army SBIR ARM26TX04-NV001 — Embedded Flight Controller Safety Kernel
 *
 * Host-side Hardware-In-The-Loop (HIL) driver that exercises the relulayer-ffi
 * C ABI through the generated relulayer.h header. The harness is intended to
 * be cross-compiled to the ARM target for on-target HIL, or compiled natively
 * for host-in-the-loop regression testing.
 */

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "relulayer.h"

#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))

static int tests_run = 0;
static int tests_passed = 0;

static void check(int condition, const char *name) {
    tests_run++;
    if (condition) {
        tests_passed++;
        printf("[PASS] %s\n", name);
    } else {
        printf("[FAIL] %s\n", name);
    }
}

static int q16_near(relulayer_q16_t a, relulayer_q16_t b, relulayer_q16_t tol) {
    relulayer_q16_t diff = a > b ? a - b : b - a;
    return diff <= tol;
}

static void test_float_q16_round_trip(void) {
    const float inputs[] = {0.0f, 1.0f, -1.0f, 0.5f, -0.5f, 3.14159265f};
    for (size_t i = 0; i < ARRAY_SIZE(inputs); i++) {
        relulayer_q16_t q = relulayer_float_to_q16(inputs[i]);
        float out = relulayer_q16_to_float(q);
        float err = fabsf(out - inputs[i]);
        check(err < 0.0001f, "float/q16 round-trip");
    }
}

static void test_phase_space_auditor(void) {
    relulayer_q16_t one = relulayer_float_to_q16(1.0f);
    relulayer_q16_t tol = relulayer_float_to_q16(0.0005f);

    check(relulayer_audit_phase_space_invariant(one) != 0, "auditor accepts det_j = 1.0");
    check(relulayer_audit_phase_space_invariant(one + tol) != 0, "auditor accepts det_j within tolerance");
    check(relulayer_audit_phase_space_invariant(one - tol) != 0, "auditor accepts det_j within tolerance");
    check(relulayer_audit_phase_space_invariant(0) == 0, "auditor rejects det_j = 0");
    check(relulayer_audit_phase_space_invariant(one + one) == 0, "auditor rejects det_j = 2.0");
}

static void test_velocity_clamping(void) {
    relulayer_q16_t v_max = relulayer_float_to_q16(5.0f);
    relulayer_q16_t half_width = relulayer_float_to_q16(100.0f);
    struct Vector3DQ16 pos = {0, 0, 0};
    struct Vector3DQ16 v_prop = {
        relulayer_float_to_q16(10.0f),
        relulayer_float_to_q16(-7.0f),
        relulayer_float_to_q16(2.0f),
    };

    struct InterceptionResult res = relulayer_process_command_vector(
        v_prop, pos, relulayer_float_to_q16(1.0f), v_max, half_width);

    check(res.auditor_passed, "clamping auditor passed");
    check(q16_near(res.v_safe.x, v_max, 1), "x clamped to +v_max");
    check(q16_near(res.v_safe.y, -v_max, 1), "y clamped to -v_max");
    check(q16_near(res.v_safe.z, relulayer_float_to_q16(2.0f), 1), "z unchanged below ceiling");
}

static void test_geofence_repulsion(void) {
    relulayer_q16_t v_max = relulayer_float_to_q16(10.0f);
    relulayer_q16_t half_width = relulayer_float_to_q16(20.0f);
    struct Vector3DQ16 pos = {
        relulayer_float_to_q16(18.0f),
        relulayer_float_to_q16(-18.0f),
        0,
    };
    struct Vector3DQ16 v_prop = {
        relulayer_float_to_q16(3.0f),
        relulayer_float_to_q16(-3.0f),
        relulayer_float_to_q16(1.0f),
    };

    struct InterceptionResult res = relulayer_process_command_vector(
        v_prop, pos, relulayer_float_to_q16(1.0f), v_max, half_width);

    check(res.auditor_passed, "geofence auditor passed");
    check(res.v_safe.x == 0, "x repulsed at +geofence wall");
    check(res.v_safe.y == 0, "y repulsed at -geofence wall");
    check(q16_near(res.v_safe.z, relulayer_float_to_q16(1.0f), 1), "z unaffected");
}

static void test_auditor_fallback(void) {
    relulayer_q16_t v_max = relulayer_float_to_q16(10.0f);
    relulayer_q16_t half_width = relulayer_float_to_q16(100.0f);
    struct Vector3DQ16 pos = {0, 0, 0};
    struct Vector3DQ16 v_prop = {
        relulayer_float_to_q16(1.0f),
        relulayer_float_to_q16(2.0f),
        relulayer_float_to_q16(3.0f),
    };

    struct InterceptionResult res = relulayer_process_command_vector(
        v_prop, pos, 0, v_max, half_width);

    check(!res.auditor_passed, "auditor failure detected");
    check(res.v_safe.x == 0 && res.v_safe.y == 0 && res.v_safe.z == 0,
          "fallback zero vector on audit failure");
    check(res.latency_cycles == 42, "fallback latency reported as 42 cycles");
}

int main(void) {
    printf("=== ReluLayer C HIL Driver Harness ===\n");
    printf("Target: ARM26TX04-NV001 Embedded Flight Controller Safety Kernel\n\n");

    test_float_q16_round_trip();
    test_phase_space_auditor();
    test_velocity_clamping();
    test_geofence_repulsion();
    test_auditor_fallback();

    printf("\n%d/%d tests passed\n", tests_passed, tests_run);
    return (tests_passed == tests_run) ? 0 : 1;
}
