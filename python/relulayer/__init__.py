"""
ReluLayer™: Deterministic Edge Governor & Real-Time Execution Gatekeeper.
"""

from relulayer._relulayer import (
    ReluBoundary,
    ReluReceipt,
    ReluViolation,
    MonotonicCounter,
    Governor,  # retained for backward-compatible scalar clamping workflows
)

__version__ = "0.2.0"
__all__ = [
    "ReluBoundary",
    "ReluReceipt",
    "ReluViolation",
    "MonotonicCounter",
    "__version__",
]
