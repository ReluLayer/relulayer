import 'dart:convert';
import 'dart:ffi';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:crypto/crypto.dart';
import 'package:ffi/ffi.dart';
import 'package:flutter_shell/ffi/bindings.dart';

void main() {
  test('GREEN PHASE: FFI Pipeline Signature Gate Verification Test', () async {
    // Clean up production DB from prior host runs to avoid "Cryptographic key verification failed" on key derivation mismatches
    final baseDir = Directory.current.path;
    for (final filename in [
      '$baseDir/veristate_production.db',
      '$baseDir/veristate_production.db-wal',
      '$baseDir/veristate_production.db-shm'
    ]) {
      final file = File(filename);
      if (file.existsSync()) {
        file.deleteSync();
      }
    }

    // 1. Replicate the Rust-side core hardware trust factors
    final hardwareSeed = List<int>.generate(32, (i) => 1);
    final challenge = utf8.encode('session-auth-challenge');

    // 2. Synthesize a valid SHA-256 Attestation Token: SHA256(seed || challenge)
    final tokenPayload = Uint8List.fromList([...hardwareSeed, ...challenge]);
    final attestationToken = sha256.convert(tokenPayload).bytes;

    // 3. Generate a valid Ed25519 signature derived using the testing cryptographic hook
    final payload = utf8.encode('CRACKED_FOUNDATION count=3');
    final native = VeriStateNative();

    final signature = native.signManifest(
      seed: hardwareSeed,
      label: utf8.encode('veristate-manifest-signing-v1'),
      payload: payload,
    );

    // 4. Fire the live FFI pipeline execution
    final Pointer<FfiFinding> findingPtr = native.executePipeline(
      rawPayload: payload,
      latitude: 29.9512,
      longitude: -90.0716,
      attestationToken: attestationToken,
      signatureBytes: signature,
    );

    // 5. Assert performance core returned correct structured parameters
    expect(findingPtr != nullptr, true, reason: 'Pipeline returned nullptr. Authentication gate failed.');

    try {
      final FFIFinding finding = findingPtr.ref;
      final damageType = finding.damage_type.cast<Utf8>().toDartString();
      
      expect(damageType, 'CRACKED_FOUNDATION');
      expect(finding.count, 3);
      expect((finding.latitude - 29.9512).abs() < 1e-6, true);
      expect((finding.longitude - (-90.0716)).abs() < 1e-6, true);
    } finally {
      // 6. Memory Protection: Immediate reclamation of heap pointer frames
      native.freeFfiFinding(findingPtr);
    }
  });
}
