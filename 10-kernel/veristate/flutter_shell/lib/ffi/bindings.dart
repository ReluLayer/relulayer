// flutter_shell/lib/ffi/bindings.dart

import 'dart:ffi';
import 'dart:io' show Platform;
import 'package:ffi/ffi.dart';

/// Mirror struct matching the exact 144-byte C-ABI layout mapped in Rust.
base class FFIFinding extends Struct {
  external Pointer<Utf8> damage_type;

  @Int32()
  external int count;

  external Pointer<Utf8> location;

  @Int64()
  external int timestamp;

  @Double()
  external double latitude;

  @Double()
  external double longitude;

  @Array(32)
  external Array<Uint8> device_attestation;

  @Array(64)
  external Array<Uint8> signature;
}

typedef FfiFinding = FFIFinding;

// Native C Function Signatures
typedef FreeFfiFindingC = Void Function(Pointer<FFIFinding> finding);
typedef FreeFfiFindingDart = void Function(Pointer<FFIFinding> finding);

typedef FfiProcessTelemetryC = Pointer<FFIFinding> Function(
  Pointer<Uint8> rawPayload,
  Int32 payloadLen,
  Double lat,
  Double lon,
  Pointer<Uint8> attestationToken,
  Int32 tokenLen,
  Pointer<Uint8> signature,
);

typedef FfiProcessTelemetryDart = Pointer<FFIFinding> Function(
  Pointer<Uint8> rawPayload,
  int payloadLen,
  double lat,
  double lon,
  Pointer<Uint8> attestationToken,
  int tokenLen,
  Pointer<Uint8> signature,
);

typedef FfiTestSignManifestC = Int32 Function(
  Pointer<Uint8> seed,
  Pointer<Uint8> label,
  Int32 labelLen,
  Pointer<Uint8> payload,
  Int32 payloadLen,
  Pointer<Uint8> sigOut,
);

typedef FfiTestSignManifestDart = int Function(
  Pointer<Uint8> seed,
  Pointer<Uint8> label,
  int labelLen,
  Pointer<Uint8> payload,
  int payloadLen,
  Pointer<Uint8> sigOut,
);

typedef FfiDispatchPendingOutboxC = Int32 Function();
typedef FfiDispatchPendingOutboxDart = int Function();

/// Core Orchestration Bridge responsible for linking cross-platform
/// compiled Rust binaries directly into the current host memory space.
class VeriStateNative {
  late final DynamicLibrary _dylib;
  late final FreeFfiFindingDart freeFfiFinding;
  late final FfiProcessTelemetryDart _processTelemetry;
  late final FfiTestSignManifestDart _testSignManifest;
  late final FfiDispatchPendingOutboxDart _dispatchPendingOutbox;

  VeriStateNative() {
    _dylib = _loadPlatformLibrary();
    _initializeSymbols();
  }

  /// Dynamically routes library loader resolution paths depending on the host OS platform target.
  DynamicLibrary _loadPlatformLibrary() {
    if (Platform.isLinux) {
      // Direct relative resolution layout targeting the local compiled debug object on the Linux host
      const String linuxPath = '../veristate-core/target/debug/libveristate_core.so';
      try {
        return DynamicLibrary.open(linuxPath);
      } catch (e) {
        // Fallback to look inside standard environment search layouts if debug object is missing
        try {
          return DynamicLibrary.open('libveristate_core.so');
        } catch (_) {
          throw Exception('FFI Boundary Failure [Linux]: Cannot open $linuxPath. Run "cargo build" inside veristate-core first. Error: $e');
        }
      }
    } else if (Platform.isWindows) {
      const String windowsPath = r'\\wsl.localhost\Ubuntu\home\iamin\veristate\veristate-core\target\x86_64-pc-windows-gnu\release\veristate_core.dll';
      try {
        return DynamicLibrary.open(windowsPath);
      } catch (e) {
        throw Exception('FFI Boundary Failure [Windows]: Cannot open $windowsPath. Error: $e');
      }
    } else if (Platform.isAndroid) {
      try {
        return DynamicLibrary.open('libveristate_core.so');
      } catch (e) {
        throw Exception('FFI Boundary Failure [Android]: Native .so initialization failed. Error: $e');
      }
    } else {
      throw UnsupportedError('Target execution platform is not bound to VeriState-Core architecture definitions.');
    }
  }

  void _initializeSymbols() {
    freeFfiFinding = _dylib
        .lookup<NativeFunction<FreeFfiFindingC>>('free_ffi_finding')
        .asFunction<FreeFfiFindingDart>();

    _processTelemetry = _dylib
        .lookup<NativeFunction<FfiProcessTelemetryC>>('ffi_process_telemetry')
        .asFunction<FfiProcessTelemetryDart>();

    _testSignManifest = _dylib
        .lookup<NativeFunction<FfiTestSignManifestC>>('ffi_test_sign_manifest')
        .asFunction<FfiTestSignManifestDart>();

    _dispatchPendingOutbox = _dylib
        .lookup<NativeFunction<FfiDispatchPendingOutboxC>>('ffi_dispatch_pending_outbox')
        .asFunction<FfiDispatchPendingOutboxDart>();
  }

  /// High-Level Cryptographic Helper to sign payload via the testing hook.
  List<int> signManifest({
    required List<int> seed,
    required List<int> label,
    required List<int> payload,
  }) {
    final Pointer<Uint8> seedBuffer = calloc<Uint8>(seed.length);
    final Pointer<Uint8> labelBuffer = calloc<Uint8>(label.length);
    final Pointer<Uint8> payloadBuffer = calloc<Uint8>(payload.length);
    final Pointer<Uint8> sigOutBuffer = calloc<Uint8>(64);

    try {
      seedBuffer.asTypedList(seed.length).setAll(0, seed);
      labelBuffer.asTypedList(label.length).setAll(0, label);
      payloadBuffer.asTypedList(payload.length).setAll(0, payload);

      final res = _testSignManifest(
        seedBuffer,
        labelBuffer,
        label.length,
        payloadBuffer,
        payload.length,
        sigOutBuffer,
      );

      if (res != 0) {
        throw Exception('Native signing failed with code $res');
      }

      return List<int>.from(sigOutBuffer.asTypedList(64));
    } finally {
      calloc.free(seedBuffer);
      calloc.free(labelBuffer);
      calloc.free(payloadBuffer);
      calloc.free(sigOutBuffer);
    }
  }

  /// High-Level Execution Wrapper passing Dart types safely across the memory boundary.
  Pointer<FfiFinding> executePipeline({
    required List<int> rawPayload,
    required double latitude,
    required double longitude,
    required List<int> attestationToken,
    required List<int> signatureBytes,
  }) {
    final Pointer<Uint8> payloadBuffer = calloc<Uint8>(rawPayload.length);
    final Pointer<Uint8> tokenBuffer = calloc<Uint8>(attestationToken.length);
    final Pointer<Uint8> signatureBuffer = calloc<Uint8>(signatureBytes.length);

    try {
      payloadBuffer.asTypedList(rawPayload.length).setAll(0, rawPayload);
      tokenBuffer.asTypedList(attestationToken.length).setAll(0, attestationToken);
      signatureBuffer.asTypedList(signatureBytes.length).setAll(0, signatureBytes);

      return _processTelemetry(
        payloadBuffer,
        rawPayload.length,
        latitude,
        longitude,
        tokenBuffer,
        attestationToken.length,
        signatureBuffer,
      );
    } finally {
      calloc.free(payloadBuffer);
      calloc.free(tokenBuffer);
      calloc.free(signatureBuffer);
    }
  }

  /// High-Level Wrapper triggering the background Git ledger synchronization and Option B DB pruning.
  int dispatchPendingOutbox() {
    return _dispatchPendingOutbox();
  }
}