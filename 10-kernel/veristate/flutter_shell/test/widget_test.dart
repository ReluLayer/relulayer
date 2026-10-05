// Basic Flutter widget smoke test for VeriStateApp.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_shell/main.dart';

void main() {
  testWidgets('VeriStateApp renders field terminal', (WidgetTester tester) async {
    // Use a desktop-sized viewport so the split-panel layout does not overflow.
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 1.0;

    // Build our app and trigger a frame.
    await tester.pumpWidget(const VeriStateApp());

    // Verify that the field terminal title is present.
    expect(find.text('VERISTATE FIELD TERMINAL'), findsOneWidget);
    expect(find.text('TELEMETRY PARAMETERS'), findsOneWidget);

    addTearDown(tester.view.reset);
  });
}
