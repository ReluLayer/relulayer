use pyo3::prelude::*;
use pyo3::types::PyModule;
use relulayer_core::{process_command_vector, Vector3DQ16, Q16};

#[inline(always)]
fn float_to_q16(val: f32) -> Q16 {
    (val * 65536.0) as i32
}

#[inline(always)]
fn q16_to_float(val: Q16) -> f32 {
    (val as f32) / 65536.0
}

#[pyfunction]
fn project_safe_velocity_py(
    v_prop_x: f32,
    v_prop_y: f32,
    v_prop_z: f32,
    pos_x: f32,
    pos_y: f32,
    pos_z: f32,
    det_j: f32,
    v_max: f32,
    geofence_half_width: f32,
) -> PyResult<(f32, f32, f32, bool, u32)> {
    let q_v_prop = Vector3DQ16 {
        x: float_to_q16(v_prop_x),
        y: float_to_q16(v_prop_y),
        z: float_to_q16(v_prop_z),
    };
    let q_pos = Vector3DQ16 {
        x: float_to_q16(pos_x),
        y: float_to_q16(pos_y),
        z: float_to_q16(pos_z),
    };

    let res = process_command_vector(
        q_v_prop,
        q_pos,
        float_to_q16(det_j),
        float_to_q16(v_max),
        float_to_q16(geofence_half_width),
    );

    Ok((
        q16_to_float(res.v_safe.x),
        q16_to_float(res.v_safe.y),
        q16_to_float(res.v_safe.z),
        res.auditor_passed,
        res.latency_cycles,
    ))
}

#[pymodule]
fn relulayer_py(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(project_safe_velocity_py, m)?)?;
    Ok(())
}
