from typing import Optional, Final

__version__: Final[str]

class ReluReceipt:
    @property
    def is_authorized(self) -> bool: ...
    @property
    def sequence_id(self) -> int: ...
    @property
    def timestamp_nanos(self) -> int: ...
    @property
    def receipt_hash(self) -> bytes: ...
    def verify(self, key: bytes) -> bool: ...

class ReluViolation(Exception):
    @property
    def axis(self) -> int: ...
    @property
    def violation_type(self) -> str: ...
    @property
    def message(self) -> str: ...

class MonotonicCounter:
    def __init__(self, initial_value: int = 0) -> None: ...
    def next_value(self) -> int: ...
    def current_value(self) -> int: ...

class ReluBoundary:
    def __init__(
        self,
        rate_limit: int = 1000,
        max_rate: float = 4.18,
        monotonic_window_size: int = 64,
        hmac_key: Optional[bytes] = None,
    ) -> None: ...
    def authorize_action(
        self,
        channel: int,
        setpoint: float,
        delta: float,
    ) -> ReluReceipt: ...
    def issue_receipt(
        self,
        nonce: bytes,
        timestamp: int,
        counter: int,
        action_id: bytes,
        payload: bytes,
    ) -> bytes: ...
    def intercept_and_authorize(
        self,
        action_id: bytes,
        payload: bytes,
        receipt: bytes,
    ) -> None: ...
