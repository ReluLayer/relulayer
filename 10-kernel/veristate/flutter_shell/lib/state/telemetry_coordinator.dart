// lib/state/telemetry_coordinator.dart

import 'dart:ffi';
import 'dart:isolate';
import 'package:ffi/ffi.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_shell/ffi/bindings.dart';

/// Immutable snapshot containing verified telemetric parameters and the
/// projected safe command from the ReLULayer active-set solver.
///
/// Fully decoupled from native C-ABI pointers and safe for UI rendering.
class TelemetryState {
  final String damageType;
  final int count;
  final String location;
  final DateTime timestamp;
  final double latitude;
  final double longitude;
  final List<int> attestationToken;

  // ReLULayer active-set solver outputs
  final double uSafe;
  final int iterations;
  final SolverStatus solverStatus;

  TelemetryState({
    required this.damageType,
    required this.count,
    required this.location,
    required this.timestamp,
    required this.latitude,
    required this.longitude,
    required this.attestationToken,
    required this.uSafe,
    required this.iterations,
    required this.solverStatus,
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

  // Inputs to the active-set solver
  final double uRaw;
  final double uMin;
  final double uMax;
  final List<double> constraintA;
  final List<double> constraintB;

  _IngestionTask({
    required this.payloadText,
    required this.lat,
    required this.lon,
    required this.token,
    required this.signature,
    required this.uRaw,
    required this.uMin,
    required this.uMax,
    required this.constraintA,
    required this.constraintB,
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
    required double uRaw,
    required double uMin,
    required double uMax,
    required List<double> constraintA,
    required List<double> constraintB,
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
      uRaw: uRaw,
      uMin: uMin,
      uMax: uMax,
      constraintA: constraintA,
      constraintB: constraintB,
    );

    try {
      // Offload the entire execution block to an independent background CPU thread
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
  /// Interacts directly with the global process memory space mapping of veristate-core
  /// and the verified ReLULayer active-set solver library.
  static TelemetryState? _executeIsolatedPipeline(_IngestionTask task) {
    // Initialize an isolated instance of the unified native dynamic library bridge
    final VeriStateNative nativeBridge = VeriStateNative();
    final ReluLayerBindings solver = ReluLayerBindings();
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

    // 3. Run the verified active-set solver on the isolated thread
    final SolverOutput output = solver.solveActiveSet(
      uRaw: task.uRaw,
      uMin: task.uMin,
      uMax: task.uMax,
      constraintA: task.constraintA,
      constraintB: task.constraintB,
    );

    try {
      final FfiFinding finding = findingPtr.ref;

      // 4. Extract parameter frames into a pure, thread-safe Dart memory snapshot
      return TelemetryState(
        damageType: finding.damage_type.cast<Utf8>().toDartString(),
        count: finding.count,
        location: finding.location.cast<Utf8>().toDartString(),
        timestamp: DateTime.fromMillisecondsSinceEpoch(finding.timestamp),
        latitude: finding.latitude,
        longitude: finding.longitude,
        attestationToken: List<int>.from(task.token),
        uSafe: output.uSafe,
        iterations: output.iterations,
        solverStatus: output.status,
      );
    } finally {
      // 5. Memory Protection: Immediate reclamation of heap pointer frames via the Rust allocator
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
