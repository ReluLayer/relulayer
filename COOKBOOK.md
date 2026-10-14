# ReluLayer Production Cookbook

This cookbook provides drop-in, runnable recipes demonstrating how to integrate ReluLayer into modern autonomous AI, multi-agent, and physical systems.

---

## Recipe 1: Securing Autonomous Agent Database & Tool Execution (TOCTOU Defense)

**Problem:** An autonomous AI agent generates and executes SQL queries or system commands. An adversary or concurrent worker attempts a Time-of-Check to Time-of-Use (TOCTOU) injection by mutating the memory buffer after the planner issues the action but before the host engine executes it.

```python
"""
Recipe 1: High-Assurance SQL Tool Calling with Cryptographic Receipt Verification
"""
import secrets
import time
from relulayer_py import ReluBoundary

# 1. Initialize the boundary with the application shared secret
SHARED_SECRET = secrets.token_bytes(32)
authority_boundary = ReluBoundary(SHARED_SECRET)
interceptor_boundary = ReluBoundary(SHARED_SECRET)


def agent_planner_issue_query(query: str, sequence_counter: int):
    action_name = b"execute_sql_query"
    payload = query.encode("utf-8")
    nonce = secrets.token_bytes(12)
    timestamp = int(time.time())

    # Issue a signed receipt proving authorization and payload integrity
    receipt = authority_boundary.issue_receipt(
        nonce, timestamp, sequence_counter, action_name, payload
    )
    return action_name, payload, receipt


def host_db_executor(action_name: bytes, payload: bytes, receipt: bytes):
    # Intercept and authorize directly before passing to the SQL engine.
    # Evaluates in 0.199 µs with zero heap allocation.
    try:
        interceptor_boundary.intercept_and_authorize(action_name, payload, receipt)
    except ValueError:
        raise PermissionError("SECURITY ALERT: Tampered payload or invalid receipt rejected!")

    # Safe to execute against the physical database
    print(f"[EXECUTED]: {payload.decode('utf-8')}")


# --- Normal Execution Flow ---
counter = 1
action, payload, receipt = agent_planner_issue_query(
    "SELECT balance FROM accounts WHERE user_id = '1042';", counter
)
host_db_executor(action, payload, receipt)

# --- Adversarial Tampering Attempt (TOCTOU Injection) ---
counter += 1
action, payload, receipt = agent_planner_issue_query(
    "SELECT balance FROM accounts WHERE user_id = '1042';", counter
)
# Malicious background thread mutates payload before execution:
tampered_payload = b"DROP TABLE accounts; --"

try:
    host_db_executor(action, tampered_payload, receipt)
except PermissionError as e:
    print(f"[BLOCKED]: {e}")
```

---

## Recipe 2: Preventing Replay Attacks Across Distributed Agent Calls

**Problem:** An adversary captures a valid signed execution receipt from network traffic or shared memory and replays it later to duplicate a transaction or re-execute a physical command.

```python
"""
Recipe 2: Enforcing Replay Monotonicity Across Distributed Multi-Agent Operations
"""
import secrets
import time
from relulayer_py import ReluBoundary

SECRET = secrets.token_bytes(32)
sender = ReluBoundary(SECRET)
receiver = ReluBoundary(SECRET)

nonce = secrets.token_bytes(12)
timestamp = int(time.time())
action_id = b"transfer_funds"


# Step 1: Execute sequence #100
receipt_100 = sender.issue_receipt(nonce, timestamp, 100, action_id, b"$500")
receiver.intercept_and_authorize(action_id, b"$500", receipt_100)
print("[+] Transaction 100 accepted.")

# Step 2: Adversary attempts to re-play sequence #100
try:
    receiver.intercept_and_authorize(action_id, b"$500", receipt_100)
    raise AssertionError("Replay should have been rejected")
except ValueError:
    print("[+] Replay attack blocked: duplicate sequence counter rejected.")

# Step 3: Adversary attempts a retrograde counter (sequence #99)
receipt_stale = sender.issue_receipt(nonce, timestamp, 99, action_id, b"$500")
try:
    receiver.intercept_and_authorize(action_id, b"$500", receipt_stale)
    raise AssertionError("Retrograde counter should have been rejected")
except ValueError:
    print("[+] Stale transaction blocked: counter did not increase monotonically.")
```

---

## Recipe 3: High-Frequency Robotics & Drone Motor Command Governor

**Problem:** An embodied reinforcement learning (RL) policy issues unconstrained motor demands that exceed ESC physical limits, risk motor flameout, or violate control margins during live flight or simulation steps.

```python
"""
Recipe 3: Sub-Microsecond Gym Step Interceptor for Real-Time Actuator Bounds
"""
import secrets
import time
import numpy as np
from relulayer_py import ReluBoundary


class ReluGovernedActuatorWrapper:
    """
    Drop-in gymnasium wrapper for robotics control loops (Isaac Gym, MuJoCo, PyBullet).
    Projects actions to safe bounds and authorizes each step with ReluLayer before
    passing it to the environment, adding no perceptible frame latency.
    """

    def __init__(self, env, shared_secret: bytes, min_throttle=0.05, max_throttle=0.95):
        self.env = env
        self.min_throttle = min_throttle
        self.max_throttle = max_throttle
        self.clamped_events = 0

        self.planner = ReluBoundary(shared_secret)
        self.controller = ReluBoundary(shared_secret)
        self.nonce = secrets.token_bytes(12)
        self.counter = 0

    def step(self, raw_action: np.ndarray):
        # Deterministic projection: clamp each actuator channel to safe envelope
        safe_action = np.clip(raw_action, self.min_throttle, self.max_throttle)
        if not np.array_equal(raw_action, safe_action):
            self.clamped_events += 1

        # ReluLayer authorizes the actuator command in <1 µs before execution
        self.counter += 1
        timestamp = int(time.time())
        action_id = b"motor_step"
        payload = safe_action.tobytes()
        receipt = self.planner.issue_receipt(
            self.nonce, timestamp, self.counter, action_id, payload
        )
        self.controller.intercept_and_authorize(action_id, payload, receipt)

        return self.env.step(safe_action)


# --- Example usage with a mocked environment ---
class MockEnv:
    def step(self, action):
        return action, 0.0, False, False, {}


env = MockEnv()
wrapped = ReluGovernedActuatorWrapper(env, secrets.token_bytes(32))
action = np.array([0.02, 0.5, 1.1], dtype=np.float32)
obs, reward, terminated, truncated, info = wrapped.step(action)
print(f"[GOVERNED STEP] raw={action} safe={obs} clamped_events={wrapped.clamped_events}")
```
