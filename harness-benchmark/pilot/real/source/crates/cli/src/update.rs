//! Fail closed until an EvCore update channel is explicitly established.

pub(crate) fn run() -> Result<(), String> {
    Err("update unavailable: no EvCore update channel is configured".into())
}
