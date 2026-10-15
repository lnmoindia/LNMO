# Iteration 12 — Phase M6 Principal app
- Screens: principal/(tabs)/{today,cover,attendance,fees,more}, principal/{att,messages,notices,students,teachers,users}, principal/student/[id], principal/teacher/[id].
- Shared: src/ui/AttendanceRegister.tsx (extracted from teacher attendance; render-loop fix), src/principal/{hooks.ts,ResetSheet.tsx}.
- Scoping is enforced by the backend (principal_scope); the mobile app just shows what the API returns.
- Deferred: over-the-counter fee collection (P2). Real-device UAT pending.
- Test with Sunrise only: thomas@ (High School), sindhu@ (Primary), password Sunrise@2026. Never modify LPGS.
- No new deps.
