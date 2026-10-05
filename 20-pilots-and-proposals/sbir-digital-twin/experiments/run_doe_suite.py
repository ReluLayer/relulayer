#!/usr/bin/env python3
"""
US ARMY SBIR TOPIC ARM26TX04-NV001: SIL MONTE CARLO EXPERIMENT HARNESS
=======================================================================
Lead Architect: Flight Control Safety & Avionics Digital Twin Suite
Target Kernel: Bare-metal ReluLayer Safety Projection (relulayer_py PyO3)
Hardware Context: AMD Ryzen 9 9950X3D / NVIDIA RTX 5090 (WSL2 Ubuntu 24.04)
"""

import os
import sys
import time
import math
import struct
import random
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Tuple, Dict, Any, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# Attempt PyO3 Native Safety Kernel Load; Fall back to Q16.16 Emulator if missing
try:
    import relulayer_py
    PYO3_AVAILABLE = True
except ImportError:
    PYO3_AVAILABLE = False


# =====================================================================
# 1. CONFIGURATION & DOMAIN TYPES
# =====================================================================

@dataclass
class UASGroup1Config:
    """Group 1/2 Tactical UAS Flight Envelope & Constraint Boundaries."""
    mass_kg: float = 4.5
    v_max: float = 25.0         # m/s
    a_max: float = 6.0          # m/s^2
    w_max: float = 1.5          # rad/s (yaw rate)
    
    # Geofence Axis-Aligned Bounding Box (AABB) [meters]
    geo_x_min: float = -300.0
    geo_x_max: float = 300.0
    geo_y_min: float = -300.0
    geo_y_max: float = 300.0
    geo_z_min: float = 10.0     # Minimum safe AGL
    geo_z_max: float = 120.0    # Maximum safe ceiling

    # CPU Clock frequency for cycle conversion (AMD Ryzen 9 9950X3D @ ~5.7 GHz)
    cpu_freq_hz: float = 5.7e9


class DOEType(Enum):
    DOE_01_NOMINAL = "Nominal Baseline Tracking"
    DOE_02_ADVERSARIAL_STEERING = "Adversarial Spoofed Commands"
    DOE_03_RTOS_JITTER = "RTOS Preemption & Latency Spikes"
    DOE_04_HPM_SEU_BITFLIP = "HPM SEU Bit-Flip (Velocity Registers)"
    DOE_05_GEOFENCE_BREACH = "Geofence Boundary Breach Vector"
    DOE_06_SENSOR_DRIFT = "GPS Drift & Inertial Sensor Noise"
    DOE_07_THRUST_DERATING = "Actuator Thrust Derating & Shear"
    DOE_08_COMBINED_STRESS = "Multi-Threat Tactical Compound Stress"


@dataclass
class KinematicState:
    """6-DOF Tactical UAV State Representation."""
    p: np.ndarray = field(default_factory=lambda: np.zeros(3))  # x, y, z [m]
    v: np.ndarray = field(default_factory=lambda: np.zeros(3))  # vx, vy, vz [m/s]
    a: np.ndarray = field(default_factory=lambda: np.zeros(3))  # ax, ay, az [m/s^2]
    euler: np.ndarray = field(default_factory=lambda: np.zeros(3)) # roll, pitch, yaw [rad]


# =====================================================================
# 2. DATA STREAMER & REAL TRAJECTORY LOADER
# =====================================================================

class TrajectoryStreamer:
    """Streams real flight trajectory data or synthesizes fallback logs."""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        
    def load_flight_log(self, filename: Optional[str] = None) -> pd.DataFrame:
        if self.data_dir.exists():
            csv_files = list(self.data_dir.glob("*.csv"))
            if csv_files and filename is None:
                df = pd.read_csv(csv_files[0])
                if {'x', 'y', 'z', 'vx', 'vy', 'vz'}.issubset(df.columns):
                    return df

        # Synthetic fallback matching TrajAir / NanoBench format
        steps = 200
        t = np.linspace(0, 40, steps)
        x = 200 * np.cos(0.1 * t)
        y = 200 * np.sin(0.1 * t)
        z = 50.0 + 5.0 * np.sin(0.2 * t)
        vx = -20 * np.sin(0.1 * t)
        vy = 20 * np.cos(0.1 * t)
        vz = 1.0 * np.cos(0.2 * t)
        
        return pd.DataFrame({'x': x, 'y': y, 'z': z, 'vx': vx, 'vy': vz, 'vz': vz})


# =====================================================================
# 3. 6-DOF TACTICAL UAV DYNAMICS ENGINE
# =====================================================================

class TacticalUAVDynamics:
    """Simulates 6-DOF UAV kinetics with saturated acceleration controls."""
    
    def __init__(self, config: UASGroup1Config, dt: float = 0.05):
        self.cfg = config
        self.dt = dt
        self.state = KinematicState()
        
    def reset(self, initial_pos: np.ndarray, initial_vel: np.ndarray):
        self.state.p = initial_pos.copy()
        self.state.v = initial_vel.copy()
        self.state.a = np.zeros(3)
        self.state.euler = np.zeros(3)

    def step(self, cmd_v: np.ndarray, disturbance_accel: np.ndarray = np.zeros(3)) -> KinematicState:
        desired_a = (cmd_v - self.state.v) / self.dt
        
        a_mag = np.linalg.norm(desired_a)
        if a_mag > self.cfg.a_max:
            desired_a = (desired_a / a_mag) * self.cfg.a_max
            
        self.state.a = desired_a + disturbance_accel
        self.state.v += self.state.a * self.dt
        
        v_mag = np.linalg.norm(self.state.v)
        if v_mag > self.cfg.v_max:
            self.state.v = (self.state.v / v_mag) * self.cfg.v_max
            
        self.state.p += self.state.v * self.dt
        return self.state


# =====================================================================
# 4. DISTURBANCE & SEU THREAT INJECTION ENGINE
# =====================================================================

class ThreatInjector:
    """Injects adversarial, RTOS, SEU, and physical anomalies."""
    
    @staticmethod
    def apply_seu_bitflip_float32(val: float) -> float:
        packed = struct.pack('f', float(val))
        int_repr = struct.unpack('I', packed)[0]
        bit_to_flip = random.randint(16, 30)
        corrupted_int = int_repr ^ (1 << bit_to_flip)
        try:
            res = struct.unpack('f', struct.pack('I', corrupted_int))[0]
            return res if not (math.isnan(res) or math.isinf(res)) else val * 10.0
        except OverflowError:
            return val * 10.0

    def corrupt_command(self, doe: DOEType, cmd_v: np.ndarray, step: int) -> Tuple[np.ndarray, float, np.ndarray]:
        corrupted_cmd = cmd_v.copy()
        latency_delay_sec = 0.0
        ext_accel_disturbance = np.zeros(3)

        if doe == DOEType.DOE_02_ADVERSARIAL_STEERING:
            if 50 <= step <= 90:
                corrupted_cmd += np.array([40.0, 40.0, 0.0])

        elif doe == DOEType.DOE_03_RTOS_JITTER:
            if random.random() < 0.25:
                latency_delay_sec = random.uniform(0.005, 0.015)

        elif doe == DOEType.DOE_04_HPM_SEU_BITFLIP:
            if step in [40, 80, 120]:
                corrupted_cmd[0] = self.apply_seu_bitflip_float32(corrupted_cmd[0])
                corrupted_cmd[1] = self.apply_seu_bitflip_float32(corrupted_cmd[1])

        elif doe == DOEType.DOE_05_GEOFENCE_BREACH:
            if step > 60:
                corrupted_cmd = np.array([35.0, 0.0, 0.0])

        elif doe == DOEType.DOE_06_SENSOR_DRIFT:
            corrupted_cmd += np.random.normal(0.0, 1.2, size=3)

        elif doe == DOEType.DOE_07_THRUST_DERATING:
            ext_accel_disturbance += np.array([-2.5, 1.5, -1.0])

        elif doe == DOEType.DOE_08_COMBINED_STRESS:
            if 40 <= step <= 100:
                corrupted_cmd[0] = self.apply_seu_bitflip_float32(corrupted_cmd[0])
                corrupted_cmd += np.array([15.0, -20.0, 5.0])
                ext_accel_disturbance += np.array([1.0, -2.0, 0.0])

        return corrupted_cmd, latency_delay_sec, ext_accel_disturbance


# =====================================================================
# 5. SAFETY GOVERNOR INTERFACE
# =====================================================================

class SafetyGovernorWrapper:
    """Interactions with relulayer_py Rust Kernel."""
    
    def __init__(self, config: UASGroup1Config):
        self.cfg = config

    def project_safe_velocity(self, cmd_v: np.ndarray, current_p: np.ndarray) -> Tuple[np.ndarray, float]:
        if PYO3_AVAILABLE:
            # PyO3 signature: (v_prop_x, v_prop_y, v_prop_z, pos_x, pos_y, pos_z,
            #                 det_j, v_max, geofence_half_width)
            result = relulayer_py.project_safe_velocity_py(
                float(cmd_v[0]),
                float(cmd_v[1]),
                float(cmd_v[2]),
                float(current_p[0]),
                float(current_p[1]),
                float(current_p[2]),
                1.0,                               # det_j
                self.cfg.v_max,                    # v_max
                self.cfg.geo_x_max                 # geofence_half_width
            )
            # PyO3 returns (safe_vx, safe_vy, safe_vz, auditor_passed, latency_cycles)
            safe_v = np.array([result[0], result[1], result[2]])
            # Report the true bare-metal #![no_std] kernel cycle count rather than Python/FFI wall time.
            kernel_cycles = float(result[4])
            return safe_v, kernel_cycles
        else:
            t_start = time.perf_counter_ns()
            safe_v = cmd_v.copy()
            margin = 15.0
            dt_lookahead = 1.0
            pred_p = current_p + safe_v * dt_lookahead
            
            if pred_p[0] > self.cfg.geo_x_max - margin:
                safe_v[0] = min(safe_v[0], (self.cfg.geo_x_max - margin - current_p[0]) / dt_lookahead)
            elif pred_p[0] < self.cfg.geo_x_min + margin:
                safe_v[0] = max(safe_v[0], (self.cfg.geo_x_min + margin - current_p[0]) / dt_lookahead)
                
            if pred_p[1] > self.cfg.geo_y_max - margin:
                safe_v[1] = min(safe_v[1], (self.cfg.geo_y_max - margin - current_p[1]) / dt_lookahead)
            elif pred_p[1] < self.cfg.geo_y_min + margin:
                safe_v[1] = max(safe_v[1], (self.cfg.geo_y_min + margin - current_p[1]) / dt_lookahead)

            v_norm = np.linalg.norm(safe_v)
            if v_norm > self.cfg.v_max:
                safe_v = (safe_v / v_norm) * self.cfg.v_max

            t_elapsed_ns = time.perf_counter_ns() - t_start
            cpu_cycles = t_elapsed_ns * (self.cfg.cpu_freq_hz / 1e9)
            return safe_v, cpu_cycles


# =====================================================================
# 6. MONTE CARLO EXPERIMENT SUITE RUNNER
# =====================================================================

class DOESuiteRunner:
    """Executes full DOE matrix across Monte Carlo trials."""
    
    def __init__(self, base_dir: Path):
        self.cfg = UASGroup1Config()
        self.streamer = TrajectoryStreamer(base_dir / "data")
        self.dynamics_unprotected = TacticalUAVDynamics(self.cfg)
        self.dynamics_protected = TacticalUAVDynamics(self.cfg)
        self.injector = ThreatInjector()
        self.governor = SafetyGovernorWrapper(self.cfg)
        
    def check_geofence_violation(self, p: np.ndarray) -> bool:
        return not (
            self.cfg.geo_x_min <= p[0] <= self.cfg.geo_x_max and
            self.cfg.geo_y_min <= p[1] <= self.cfg.geo_y_max and
            self.cfg.geo_z_min <= p[2] <= self.cfg.geo_z_max
        )

    def run_suite(self, mc_trials: int = 50) -> Dict[DOEType, Dict[str, Any]]:
        raw_df = self.streamer.load_flight_log()
        results = {}

        print(f"\n=======================================================================")
        print(f" STARTING MONTE CARLO SIL EXECUTION [PyO3 Native Active: {PYO3_AVAILABLE}]")
        print(f" Running {len(DOEType)} DOEs x {mc_trials} Trials Each...")
        print(f"=======================================================================\n")

        for doe in DOEType:
            unprotected_violations = 0
            protected_violations = 0
            cycles_list = []
            kinematic_deviations = []
            
            unprotected_trajectories = []
            protected_trajectories = []

            for trial in range(mc_trials):
                init_p = np.array([raw_df.iloc[0]['x'], raw_df.iloc[0]['y'], raw_df.iloc[0]['z']])
                init_v = np.array([raw_df.iloc[0]['vx'], raw_df.iloc[0]['vy'], raw_df.iloc[0]['vz']])

                self.dynamics_unprotected.reset(init_p, init_v)
                self.dynamics_protected.reset(init_p, init_v)

                unprot_p_hist = []
                prot_p_hist = []
                
                unprot_violated = False
                prot_violated = False

                for step in range(len(raw_df)):
                    target_v = np.array([
                        raw_df.iloc[step]['vx'],
                        raw_df.iloc[step]['vy'],
                        raw_df.iloc[step]['vz']
                    ])

                    cmd_v, jitter_delay, dist_a = self.injector.corrupt_command(doe, target_v, step)

                    # 1. Unprotected Execution
                    st_u = self.dynamics_unprotected.step(cmd_v, dist_a)
                    unprot_p_hist.append(st_u.p.copy())
                    if self.check_geofence_violation(st_u.p):
                        unprot_violated = True

                    # 2. Protected Execution via ReluLayer
                    safe_v, cycles = self.governor.project_safe_velocity(cmd_v, self.dynamics_protected.state.p)
                    cycles_list.append(cycles + (jitter_delay * self.cfg.cpu_freq_hz))
                    
                    st_p = self.dynamics_protected.step(safe_v, dist_a)
                    prot_p_hist.append(st_p.p.copy())
                    if self.check_geofence_violation(st_p.p):
                        prot_violated = True

                    kinematic_deviations.append(np.linalg.norm(st_p.v - target_v))

                if unprot_violated:
                    unprotected_violations += 1
                if prot_violated:
                    protected_violations += 1

                if trial == 0:
                    unprotected_trajectories = np.array(unprot_p_hist)
                    protected_trajectories = np.array(prot_p_hist)

            zero_violation_rate = ((mc_trials - protected_violations) / mc_trials) * 100.0
            avg_cycles = float(np.mean(cycles_list))
            avg_dev = float(np.mean(kinematic_deviations))

            results[doe] = {
                "unprotected_violation_pct": (unprotected_violations / mc_trials) * 100.0,
                "zero_violation_rate": zero_violation_rate,
                "avg_cpu_cycles": avg_cycles,
                "avg_kinematic_dev_m_s": avg_dev,
                "sample_unprotected_traj": unprotected_trajectories,
                "sample_protected_traj": protected_trajectories
            }

            print(f"[{doe.name}] Success Rate: {zero_violation_rate:.1f}% | "
                  f"Avg Latency: {avg_cycles:.1f} Cycles | Kinematic Dev: {avg_dev:.2f} m/s")

        return results


# =====================================================================
# 7. EXPORT & PUBLICATION-QUALITY VISUALIZATION
# =====================================================================

class ResultsExporter:
    """Generates LaTeX tables and Matplotlib vector plots."""

    @staticmethod
    def export_latex_table(results: Dict[DOEType, Dict[str, Any]], output_path: Path):
        latex_str = [
            "\\begin{table}[htbp]",
            "\\centering",
            "\\caption{ReluLayer SIL Monte Carlo Stress Suite Results (Group 1/2 UAS)}",
            "\\label{tab:relulayer_doe_results}",
            "\\begin{tabular}{lcccc}",
            "\\hline",
            "\\textbf{DOE Experiment} & \\textbf{Baseline Viol. (\\%)} & \\textbf{ReluLayer ZVR (\\%)} & \\textbf{Latency (Cycles)} & \\textbf{Kin. Dev (m/s)} \\\\",
            "\\hline"
        ]

        for doe, res in results.items():
            name_clean = doe.value.replace("&", "\\&")
            latex_str.append(
                f"{name_clean} & {res['unprotected_violation_pct']:.1f}\\% & "
                f"\\textbf{{{res['zero_violation_rate']:.1f}\\%}} & "
                f"{res['avg_cpu_cycles']:.0f} & "
                f"{res['avg_kinematic_dev_m_s']:.2f} \\\\"
            )

        latex_str.extend([
            "\\hline",
            "\\end{tabular}",
            "\\end{table}"
        ])

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write("\n".join(latex_str))
        print(f"\n[+] Saved LaTeX Summary Table to: {output_path}")

    @staticmethod
    def generate_figures(results: Dict[DOEType, Dict[str, Any]], fig_path: Path):
        fig_path.parent.mkdir(parents=True, exist_ok=True)
        
        plt.style.use('seaborn-v0_8-paper' if 'seaborn-v0_8-paper' in plt.style.available else 'default')
        fig = plt.figure(figsize=(14, 10), dpi=300)
        gs = gridspec.GridSpec(2, 2, figure=fig)

        ax1 = fig.add_subplot(gs[0, 0])
        res_doe5 = results[DOEType.DOE_05_GEOFENCE_BREACH]
        unprot = res_doe5["sample_unprotected_traj"]
        prot = res_doe5["sample_protected_traj"]

        ax1.plot(unprot[:, 0], unprot[:, 1], 'r--', label='Unprotected (Breaches Geofence)', linewidth=1.5)
        ax1.plot(prot[:, 0], prot[:, 1], 'g-', label='ReluLayer Shielded', linewidth=2.0)
        ax1.axvline(x=300.0, color='k', linestyle=':', label='Geofence Max X Boundary')
        ax1.set_title("DOE-05 Trajectory Safety Projection", fontsize=11, fontweight='bold')
        ax1.set_xlabel("X Position (m)")
        ax1.set_ylabel("Y Position (m)")
        ax1.grid(True, linestyle='--', alpha=0.6)
        ax1.legend(loc='upper left')

        ax2 = fig.add_subplot(gs[0, 1])
        doe_names = [f"DOE-0{i+1}" for i in range(len(DOEType))]
        unprot_rates = [res["unprotected_violation_pct"] for res in results.values()]
        prot_rates = [res["zero_violation_rate"] for res in results.values()]

        x = np.arange(len(doe_names))
        width = 0.35
        ax2.bar(x - width/2, unprot_rates, width, label='Unprotected Violations (%)', color='#e74c3c')
        ax2.bar(x + width/2, prot_rates, width, label='ReluLayer Shielded ZVR (%)', color='#2ecc71')
        ax2.set_title("Zero-Violation Rate (ZVR) Across DOE Matrix", fontsize=11, fontweight='bold')
        ax2.set_xticks(x)
        ax2.set_xticklabels(doe_names, rotation=45)
        ax2.set_ylabel("Percentage (%)")
        ax2.set_ylim(0, 115)
        ax2.grid(True, axis='y', linestyle='--', alpha=0.6)
        ax2.legend(loc='lower right')

        ax3 = fig.add_subplot(gs[1, 0])
        cycles = [res["avg_cpu_cycles"] for res in results.values()]
        ax3.plot(doe_names, cycles, marker='o', color='#3498db', linewidth=2, markersize=6)
        ax3.axhline(y=128, color='r', linestyle='--', label='128 Cycle Bare-Metal Target')
        ax3.set_title("Execution Overhead (CPU Cycles)", fontsize=11, fontweight='bold')
        ax3.set_ylabel("Cycles")
        ax3.grid(True, linestyle='--', alpha=0.6)
        ax3.legend()

        ax4 = fig.add_subplot(gs[1, 1])
        devs = [res["avg_kinematic_dev_m_s"] for res in results.values()]
        ax4.bar(doe_names, devs, color='#9b59b6', alpha=0.85, width=0.5)
        ax4.set_title("Mean Kinematic Velocity Deviation", fontsize=11, fontweight='bold')
        ax4.set_ylabel("Velocity Error (m/s)")
        ax4.grid(True, axis='y', linestyle='--', alpha=0.6)

        plt.tight_layout()
        plt.savefig(fig_path, dpi=300)
        print(f"[+] Saved Publication Figure Suite to: {fig_path}")


# =====================================================================
# 8. ENTRYPOINT
# =====================================================================

def main():
    workspace_root = Path.home() / "projects/sbir-digital-twin"
    runner = DOESuiteRunner(workspace_root)
    
    results = runner.run_suite(mc_trials=50)

    latex_path = workspace_root / "results" / "tables" / "doe_summary_table.tex"
    fig_path = workspace_root / "results" / "figures" / "doe_performance_metrics.png"

    ResultsExporter.export_latex_table(results, latex_path)
    ResultsExporter.generate_figures(results, fig_path)


if __name__ == "__main__":
    main()
