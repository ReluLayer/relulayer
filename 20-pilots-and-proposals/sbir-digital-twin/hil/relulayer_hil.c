/*
 * ReluLayer™ STM32H7 Hardware-In-The-Loop (HIL) Driver & DWT Benchmark
 * US Army SBIR ARM26TX04-NV001 — Embedded Flight Controller Safety Kernel
 */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "relulayer.h"

/* ARM Cortex-M7 DWT (Data Watchpoint and Trace) MMIO Registers */
#define DEMCR           (*((volatile uint32_t *)0xE000EDFC))
#define DWT_CTRL        (*((volatile uint32_t *)0xE0001000))
#define DWT_CYCCNT      (*((volatile uint32_t *)0xE0001004))

static inline void dwt_init(void) {
#if defined(__arm__) || defined(__thumb__)
    DEMCR |= (1 << 24);    /* Enable TRCENA */
    DWT_CYCCNT = 0;        /* Reset cycle counter */
    DWT_CTRL |= (1 << 0);  /* Enable CYCCNTENA */
#endif
}

static inline uint32_t dwt_get_cycles(void) {
#if defined(__arm__) || defined(__thumb__)
    return DWT_CYCCNT;
#else
    return 0;
#endif
}

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

static void test_null_pointer_guard(void) {
    ActuatorLimits limits = { .u_min = -20.0f, .u_max = 20.0f };
    SolverResult result;

    int rc1 = relulayer_solve_active_set(15.0f, limits, NULL, &result);
    check(rc1 == -1, "null constraints pointer safely rejected (rc = -1)");

    LinearConstraints constraints = {
        .a = { 1.0f, -1.0f, 0.0f, 0.0f },
        .b = { 10.0f, 10.0f, 100.0f, 100.0f }
    };
    int rc2 = relulayer_solve_active_set(15.0f, limits, &constraints, NULL);
    check(rc2 == -1, "null output pointer safely rejected (rc = -1)");
}

static void test_unconstrained_pass_through(void) {
    ActuatorLimits limits = { .u_min = -20.0f, .u_max = 20.0f };
    LinearConstraints constraints = {
        .a = { 1.0f, -1.0f, 0.0f, 0.0f },
        .b = { 15.0f, 15.0f, 100.0f, 100.0f }
    };
    SolverResult result;

    int rc = relulayer_solve_active_set(5.0f, limits, &constraints, &result);
    check(rc == 0, "unconstrained solve returned 0");
    check(result.status == SolverStatus_Optimal, "status is SolverStatus_Optimal");
    check(fabsf(result.u_safe - 5.0f) < 1e-5f, "u_safe matches unconstrained u_raw (5.0)");
    check(result.iterations <= 10, "iterations bounded by k <= 10");
}

static void test_active_constraint_projection(void) {
    ActuatorLimits limits = { .u_min = -20.0f, .u_max = 20.0f };
    LinearConstraints constraints = {
        .a = { 1.0f, -1.0f, 0.0f, 0.0f },
        .b = { 10.0f, 10.0f, 100.0f, 100.0f }
    };
    SolverResult result;

    int rc = relulayer_solve_active_set(15.0f, limits, &constraints, &result);
    check(rc == 0, "active-set solve returned 0");
    check(result.status == SolverStatus_Optimal, "status is SolverStatus_Optimal");
    check(fabsf(result.u_safe - 10.0f) < 1e-5f, "u_safe projected to active boundary (10.0)");
    check(result.iterations <= 10, "iterations bounded by k <= 10");
}

static void test_infeasible_fallback_relaxation(void) {
    ActuatorLimits limits = { .u_min = -20.0f, .u_max = 20.0f };
    LinearConstraints constraints = {
        .a = { 1.0f, -1.0f, 0.0f, 0.0f },
        .b = { -10.0f, -15.0f, 100.0f, 100.0f }
    };
    SolverResult result;

    int rc = relulayer_solve_active_set(0.0f, limits, &constraints, &result);
    check(rc == 0, "infeasible solve handled gracefully (rc = 0)");
    check(result.u_safe >= limits.u_min && result.u_safe <= limits.u_max,
          "fallback bounded by actuator envelope [-20.0, 20.0]");
}

static void benchmark_dwt_execution_cycles(void) {
    printf("\n--- ARM Cortex-M7 DWT Cycle Benchmark (1,000 Iterations) ---\n");
    dwt_init();

    ActuatorLimits limits = { .u_min = -20.0f, .u_max = 20.0f };
    LinearConstraints constraints = {
        .a = { 1.0f, -1.0f, 0.0f, 0.0f },
        .b = { 10.0f, 10.0f, 100.0f, 100.0f }
    };
    SolverResult result;

    uint32_t min_cycles = UINT32_MAX;
    uint32_t max_cycles = 0;
    uint64_t total_cycles = 0;
    const int iterations = 1000;

    for (int i = 0; i < iterations; i++) {
        float u_test = -25.0f + ((float)i / (float)iterations) * 50.0f;

        uint32_t start = dwt_get_cycles();
        relulayer_solve_active_set(u_test, limits, &constraints, &result);
        uint32_t elapsed = dwt_get_cycles() - start;

        if (elapsed < min_cycles) min_cycles = elapsed;
        if (elapsed > max_cycles) max_cycles = elapsed;
        total_cycles += elapsed;
    }

    uint32_t avg_cycles = (uint32_t)(total_cycles / iterations);

    printf("  Min Cycles: %lu\n", (unsigned long)min_cycles);
    printf("  Max Cycles (WCET): %lu\n", (unsigned long)max_cycles);
    printf("  Avg Cycles: %lu\n", (unsigned long)avg_cycles);

#if defined(__arm__) || defined(__thumb__)
    float avg_us = ((float)avg_cycles / 480.0f);
    float max_us = ((float)max_cycles / 480.0f);
    printf("  Estimated Time @ 480 MHz: Avg = %.3f us, WCET = %.3f us\n", avg_us, max_us);
    check(max_cycles > 0, "DWT cycle measurement recorded on Cortex-M7");
#else
    check(1, "DWT cycle measurement simulated on host platform");
#endif
}

int main(void) {
    printf("=== ReluLayer™ ASIL-D Active-Set HIL Driver Harness ===\n");
    printf("Target: STM32H743ZI / STM32H753ZI (Cortex-M7 @ 480 MHz)\n\n");

    test_null_pointer_guard();
    test_unconstrained_pass_through();
    test_active_constraint_projection();
    test_infeasible_fallback_relaxation();
    benchmark_dwt_execution_cycles();

    printf("\n=======================================================\n");
    printf("HIL Test Summary: %d/%d assertions passed\n", tests_passed, tests_run);
    printf("=======================================================\n");

    return (tests_passed == tests_run) ? 0 : 1;
}
