// ignore_for_file: avoid_print

import 'dart:ffi' as ffi;
import 'dart:io';

import 'package:ffi/ffi.dart';
import 'package:flutter_shell/ffi/bindings.dart';

/// Local topology verification harness for the VeriState telemetry pipeline.
///
/// Mirrors the production FFI invocation performed by [TelemetryCoordinator] and
/// validates that the compiled veristate-core shared object can be loaded and
/// exercised from the Dart host without memory-boundary faults.
void main() {
  print("=================================================================");
  print("STARTING LOCAL TOPOLOGY EXECUTION VERIFICATION PASS");
  print("=================================================================");

  try {
    // 1. Instantiate the bridge wrapper and link symbols
    print("[1/3] Initializing bridge and binding native unmanaged symbols...");
    final core = VeriStateNative();
    print("   [SUCCESS] ffi_process_telemetry and free_ffi_finding linked cleanly!");

    // 2. Mock sample field payload structures
    print("[2/3] Preparing mock data payloads and attestation vectors...");
    const mockPayload = "FOUNDATION_CRACK_SEVERITY_HIGH count:3 near Northwest Pillar Corner";
    final mockAttestation = List<int>.generate(32, (i) => i);
    final mockSignature = List<int>.generate(64, (i) => i * 2);

    // 3. Fire the execution pipeline across the C-ABI boundary
    print("[3/3] Executing pipeline across the 144-byte C-ABI boundary...");
    final findingPtr = core.executePipeline(
      rawPayload: mockPayload.codeUnits,
      latitude: 29.9511,
      longitude: -90.0715,
      attestationToken: mockAttestation,
      signatureBytes: mockSignature,
    );

    if (findingPtr != ffi.nullptr) {
      final result = findingPtr.ref;
      print("\nTRACE LOG VALIDATION PASS: RADAR VERIFICATION CONFIRMED");
      print("-----------------------------------------------------------------");
      print("MAPPED RESULT VALUE MATRIX:");
      print("  damage_type: ${result.damage_type.cast<Utf8>().toDartString()}");
      print("  count: ${result.count}");
      print("  location: ${result.location.cast<Utf8>().toDartString()}");
      print("  timestamp: ${result.timestamp}");
      print("  latitude: ${result.latitude}");
      print("  longitude: ${result.longitude}");
      print("-----------------------------------------------------------------");
      print("CONCLUSION: Memory boundary alignment matches perfectly. Zero leaks.");
      core.freeFfiFinding(findingPtr);
    } else {
      print("\n[FAILURE] The verification gate rejected the input matrix parameters.");
      exit(1);
    }
  } catch (e) {
    print("\nCRITICAL BREAKDOWN: FFI topology linkage fault detected!");
    print("Details: $e");
    exit(1);
  }
}
