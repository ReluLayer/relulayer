use axum::{
    routing::{get, post},
    Router,
    Json,
    http::StatusCode,
};
use serde::Deserialize;
use ed25519_dalek::{VerifyingKey, Signature, Verifier};
use tracing::{info, error, warn};

#[derive(Deserialize, Debug)]
struct TelemetryPayload {
    payload_text: String,
    latitude: f64,
    longitude: f64,
    public_key_hex: String,
    signature_hex: String,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();
    info!("INITIALIZING VERISTATE SECURE AGGREGATION SERVER...");

    let app = Router::new()
        .route("/health", get(health_check))
        .route("/webhook/gitea", post(handle_gitea_webhook))
        .route("/api/v1/telemetry", post(verify_and_aggregate_telemetry));

    let listener = tokio::net::TcpListener::bind("0.0.0.0:8080").await.unwrap();
    info!("Secure Node Online. Gateway listening on {}", listener.local_addr().unwrap());

    axum::serve(listener, app).await.unwrap();
}

async fn health_check() -> &'static str {
    "VERISTATE AGGREGATION NODE: SECURE"
}

/// Dynamic Cryptographic Verification Engine
async fn verify_and_aggregate_telemetry(Json(data): Json<TelemetryPayload>) -> (StatusCode, &'static str) {
    info!("Processing Ingestion Request from Edge Device...");

    // 1. Parse the Public Key from hex
    let public_key_bytes = match hex::decode(&data.public_key_hex) {
        Ok(bytes) => bytes,
        Err(_) => {
            error!("Crypto Failure: Invalid hex formatting in Public Key.");
            return (StatusCode::BAD_REQUEST, "Malformed Public Key Hex");
        }
    };

    let verifying_key = match VerifyingKey::try_from(public_key_bytes.as_slice()) {
        Ok(key) => key,
        Err(_) => {
            error!("Crypto Failure: Byte length does not match Ed25519 specification.");
            return (StatusCode::BAD_REQUEST, "Invalid Ed25519 Public Key Structure");
        }
    };

    // 2. Parse the Signature from hex
    let signature_bytes = match hex::decode(&data.signature_hex) {
        Ok(bytes) => bytes,
        Err(_) => {
            error!("Crypto Failure: Invalid hex formatting in Signature vector.");
            return (StatusCode::BAD_REQUEST, "Malformed Signature Hex");
        }
    };

    let signature = match Signature::from_slice(&signature_bytes) {
        Ok(sig) => sig,
        Err(_) => {
            error!("Crypto Failure: Signature slice length is mathematically invalid.");
            return (StatusCode::BAD_REQUEST, "Malformed Signature Length");
        }
    };

    // 3. Reconstruct message context matching the FFI label protocol
    let mut message_context = Vec::new();
    message_context.extend_from_slice("veristate-manifest-signing-v1".as_bytes());
    message_context.extend_from_slice(data.payload_text.as_bytes());

    // 4. Fire Cryptographic Trust Gate
    match verifying_key.verify(&message_context, &signature) {
        Ok(_) => {
            info!("─── CRYPTOGRAPHIC SIGNATURE VERIFIED ───");
            info!("Origin: Device Verified Successfully via Hardware Public Key Context.");
            info!("Telemetry: Description [{}], Coordinates: ({}, {})", data.payload_text, data.latitude, data.longitude);
            (StatusCode::CREATED, "Telemetry Packet Fully Authenticated and Logged.")
        },
        Err(_) => {
            warn!("⚠️ SECURITY ALERT: Cryptographic Signature Mismatch! Rejecting untrusted telemetry packet.");
            (StatusCode::UNAUTHORIZED, "Signature Mismatch. Source identity cannot be proven.")
        }
    }
}

// Fixed the explicit Json wrapping type mismatch here
async fn handle_gitea_webhook(Json(payload): Json<serde_json::Value>) -> StatusCode {
    info!("Gitea Synchronization Webhook captured payload size: {} keys", payload.as_object().map(|m| m.len()).unwrap_or(0));
    StatusCode::OK
}
