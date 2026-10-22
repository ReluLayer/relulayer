"""
ReluLayer™: Deterministic zero-heap agent governor and execution gatekeeper
for software agent workflows and simulation testbeds.

IMPORTANT NOTICE: This package is distributed solely as an experimental
evaluation and development framework for software-level agent governance,
simulation, and architectural prototyping. It is NOT CERTIFIED FOR
SAFETY-CRITICAL, HIGH-CONSEQUENCE, OR LIFE-CRITICAL SYSTEMS.
"""

from relulayer._relulayer import (
    ReluBoundary,
    ReluReceipt,
    ReluViolation,
    MonotonicCounter,
    Governor,  # retained for backward-compatible scalar clamping workflows
)

__version__ = "0.2.1"
__all__ = [
    "ReluBoundary",
    "ReluReceipt",
    "ReluViolation",
    "MonotonicCounter",
    "__version__",
]
