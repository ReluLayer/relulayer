//! ReluLayer™ Enterprise Fleet Control Plane
//!
//! Copyright (c) 2026 Ishmael Amin. All rights reserved.
//! Commercial license required for multi-node and fleet orchestration.

pub struct FleetMonotonicSequencer {
    node_id: u64,
    current_epoch: u64,
}

impl FleetMonotonicSequencer {
    pub fn new(node_id: u64) -> Self {
        Self {
            node_id,
            current_epoch: 1,
        }
    }

    pub fn node_id(&self) -> u64 {
        self.node_id
    }

    pub fn current_epoch(&self) -> u64 {
        self.current_epoch
    }
}
