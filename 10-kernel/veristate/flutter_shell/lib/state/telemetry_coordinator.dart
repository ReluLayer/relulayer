// lib/state/telemetry_coordinator.dart

import 'dart:ffi';
import 'dart:isolate';
import 'package:ffi/ffi.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_shell/ffi/bindings.dart';

/// Immutable snapshot containing verified telemetric parameters 
/// fully decoupled from native C-ABI pointers. Safe for UI rendering.
class TelemetryState {
  final String damageType;
  final int count;
  final String location;
  final DateTime timestamp;
  final double latitude;
  final double longitude;
  final List<int> attestationToken;

  TelemetryState({
    required this.damageType,
    required this.count,
    required this.location,
    required this.timestamp,
    required this.latitude,
    required this.longitude,
    required this.attestationToken,
  });
}

/// Internal configuration container used to transfer parameters safely
/// across the isolate background worker boundary.
class _IngestionTask {
  final String payloadText;
  final double lat;
  final double lon;
  final List<int> token;
  final List<int> signature;

  _IngestionTask({
    required this.payloadText,
    required this.lat,
    required this.lon,
    required this.token,
    required this.signature,
  });
}

/// Architectural Coordinator layer transforming raw binary FFI buffers 
/// into reactive, change-notified UI state snapshots via background Isolates.
class TelemetryCoordinator extends ChangeNotifier {
  TelemetryState? _latestState;
  bool _isProcessing = false;

  /// Exposes the current verified telemetry block to presentation widgets.
  TelemetryState? get latestState => _latestState;

  /// Exposes the processing state flag to drive UI loading indicators.
  bool get isProcessing => _isProcessing;

  /// Ingests parameters, offloads the cryptographic engine workload to an isolated 
  /// background OS thread, and updates the reactive tree upon completion.
  Future<void> processIncomingStream({
    required String payloadText,
    required double lat,
    required double lon,
    required List<int> token,
    required List<int> signature,
  }) async {
    // Prevent overlapping execution transactions
    if (_isProcessing) return;

    _isProcessing = true;
    notifyListeners();

    final task = _IngestionTask(
      payloadText: payloadText,
      lat: lat,
      lon: lon,
      token: token,
      signature: signature,
    );

    try {
      // Offload the entire 5.15ms execution block to an independent background CPU thread
      final TelemetryState? resultState = await Isolate.run(() => _executeIsolatedPipeline(task));
      _latestState = resultState;
    } catch (e) {
      _latestState = null;
      debugPrint("Isolate Processing Boundary Failure: $e");
    } finally {
      _isProcessing = false;
      notifyListeners();
    }
  }

  /// Top-Level isolated execution block. Runs entirely on a background OS thread.
  /// Interacts directly with the global process memory space mapping of veristate-core.
  static TelemetryState? _executeIsolatedPipeline(_IngestionTask task) {
    // Initialize an isolated instance of the unified native dynamic library bridge
    final VeriStateNative nativeBridge = VeriStateNative();
    final List<int> rawPayload = task.payloadText.codeUnits;

    // 1. Fire execution transaction across into the compiled Rust Core
    final Pointer<FfiFinding> findingPtr = nativeBridge.executePipeline(
      rawPayload: rawPayload,
      latitude: task.lat,
      longitude: task.lon,
      attestationToken: task.token,
      signatureBytes: task.signature,
    );

    // 2. Intercept atomic null failure conditions
    if (findingPtr == nullptr) {
      return null;
    }

    try {
      final FfiFinding finding = findingPtr.ref;

      // 3. Extract parameter frames into a pure, thread-safe Dart memory snapshot
      return TelemetryState(
        damageType: finding.damage_type.cast<Utf8>().toDartString(),
        count: finding.count,
        location: finding.location.cast<Utf8>().toDartString(),
        timestamp: DateTime.fromMillisecondsSinceEpoch(finding.timestamp),
        latitude: finding.latitude,
        longitude: finding.longitude,
        attestationToken: List<int>.from(task.token),
      );
    } finally {
      // 4. Memory Protection: Immediate reclamation of heap pointer frames via the Rust allocator
      nativeBridge.freeFfiFinding(findingPtr);
    }
  }

  /// Triggers the native Rust background worker to dispatch pending outbox
  /// records to the Git ledger and execute the Option B database pruning loop.
  /// Runs on an isolated OS thread to prevent UI jank during network I/O.
  Future<int> triggerLedgerSync() async {
    try {
      return await Isolate.run(() {
        final VeriStateNative nativeBridge = VeriStateNative();
        // Calls into the C-ABI gateway which invokes dispatch_pending_outbox
        return nativeBridge.dispatchPendingOutbox(); 
      });
    } catch (e) {
      debugPrint("Ledger Sync Isolate Failure: $e");
      return 0;
    }
  }
}