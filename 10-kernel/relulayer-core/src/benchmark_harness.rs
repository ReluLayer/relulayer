pub struct BenchmarkReport {
    pub start_cycles: u32,
    pub end_cycles: u32,
    pub elapsed_cycles: u32,
    pub elapsed_nanoseconds: u32,
}

pub struct HardwareCycleCounter;

impl HardwareCycleCounter {
    #[allow(unsafe_code)]
    pub fn init() {
        #[cfg(any(target_arch = "arm", target_arch = "aarch64"))]
        unsafe {
            const DEMCR: *mut u32 = 0xE000_EDFC as *mut u32;
            core::ptr::write_volatile(DEMCR, core::ptr::read_volatile(DEMCR) | (1 << 24));
            const DWT_CYCCNT: *mut u32 = 0xE000_1004 as *mut u32;
            core::ptr::write_volatile(DWT_CYCCNT, 0);
        }
    }

    #[inline(always)]
    #[allow(unsafe_code)]
    pub fn read_cycles() -> u32 {
        #[cfg(any(target_arch = "arm", target_arch = "aarch64"))]
        unsafe {
            let dwt_cyccnt = 0xE000_1004 as *const u32;
            core::ptr::read_volatile(dwt_cyccnt)
        }
        #[cfg(not(any(target_arch = "arm", target_arch = "aarch64")))]
        {
            0
        }
    }

    pub fn measure<F, R>(f: F) -> (R, BenchmarkReport)
    where
        F: FnOnce() -> R,
    {
        Self::init();
        let start = Self::read_cycles();
        let result = f();
        let end = Self::read_cycles();
        let elapsed = end.wrapping_sub(start);
        let elapsed_ns = (elapsed as u64 * 125u64 / 21u64) as u32;
        let report = BenchmarkReport {
            start_cycles: start,
            end_cycles: end,
            elapsed_cycles: elapsed,
            elapsed_nanoseconds: elapsed_ns,
        };
        (result, report)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cycle_measurement() {
        let (_res, report) = HardwareCycleCounter::measure(|| {
            let mut sum = 0u32;
            for i in 0..100 {
                sum = sum.wrapping_add(i);
            }
            sum
        });
        let _ = report.elapsed_cycles;
    }
}
