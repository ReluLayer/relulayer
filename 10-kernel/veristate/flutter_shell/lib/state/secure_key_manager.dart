// lib/state/secure_key_manager.dart

import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureKeyManager {
  static const _storage = FlutterSecureStorage();
  static const _seedKey = 'veristate_hardware_seed_v1';

  /// Interrogates the native OS Keystore/Keychain.
  /// If no seed exists (first boot), generates 32 secure random bytes and locks them away.
  static Future<List<int>> getOrGenerateSeed() async {
    try {
      final existingSeedHex = await _storage.read(key: _seedKey);

      if (existingSeedHex != null) {
        debugPrint("SecureKeyManager: Hardware seed retrieved from OS Keystore.");
        return _hexToBytes(existingSeedHex);
      }

      debugPrint("SecureKeyManager: First boot detected. Generating secure hardware seed...");
      
      // Generate 32 cryptographically secure random bytes
      final random = Random.secure();
      final newSeed = List<int>.generate(32, (_) => random.nextInt(256));

      // Lock the new seed into the OS Keystore as a hex string
      await _storage.write(key: _seedKey, value: _bytesToHex(newSeed));
      
      debugPrint("SecureKeyManager: Seed locked in OS Keystore.");
      return newSeed;
    } catch (e) {
      debugPrint("CRITICAL: Failed to access secure storage: $e");
      // Fallback for extreme hardware failure cases, though this should ideally halt execution
      throw Exception('Secure Storage Fault: Unable to retrieve or generate cryptographic seed.');
    }
  }

  static String _bytesToHex(List<int> bytes) {
    return bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('');
  }

  static List<int> _hexToBytes(String hex) {
    List<int> bytes = [];
    for (int i = 0; i < hex.length; i += 2) {
      bytes.add(int.parse(hex.substring(i, i + 2), radix: 16));
    }
    return bytes;
  }
}