# Mobile commit log

## Iteration 1 — Phase M1: Expo foundation + Parent app
- **Commit**: base b5aba76 (changes uncommitted at time of writing; auto-commit follows)
- **Date**: 2026-10-14
- **Changes**:
  - Bootstrapped /app/mobile from /opt/mono-template/mobile (Expo SDK 57, expo-router), extracted node_modules, kept EXPO_PUBLIC_BACKEND_URL.
  - App name LNMO, scheme `lnmo`, LNMO mark icon/adaptive icon on white, splash logo, camera/photo permissions, Android https intent filter for /login and /setup/parent.
  - Auth via Bearer token (X-Client: mobile), tokens in expo-secure-store; refresh; PASSWORD_CHANGE_REQUIRED → /change-password.
  - School code selection + deep link /login/<code>, branded login, lockout/invalid messages, setup-link flow /setup/parent/<token>.
  - Parent tabs: Home, Timetable, Fees, Messages, More (+ invoice, proof, issue, thread, new-message, more/* screens).
  - Chat WebSocket /api/ws/chat?token= with polling fallback, typing, seen, image/PDF attachments.
- **Backend changes (additive)**: server.py — `with_mobile_tokens()`; login/change-password/parent-setup/parent-register return access_token+refresh_token when `X-Client: mobile`; /auth/refresh accepts body refresh_token for mobile; get_current_user accepts `?token=` only on /api/ws/chat.
- **Files modified**: mobile/** (new), backend/server.py
- **Web files referenced**: frontend/src/App.js, lib/api.js, lib/chatSocket.js, lib/fees.js, context/AuthContext.jsx, context/ReportIssue.jsx, pages/LoginPage.jsx, pages/ParentSetupPage.jsx, pages/institution/ChangePasswordPage.jsx, pages/parent/*, pages/portal/*, components/chat/ChatThread.jsx, components/homework/HomeworkList.jsx, components/common/ReportIssueDialog.jsx

## Iteration 2 — Phone login fix (LPGS parent on Expo Go)
- **Commit**: (after b5aba76; auto-commit)
- **Date**: 2026-10-14
- **Changes**:
  - Mobile: identifier input keyboardType="email-address" on ALL platforms (was iOS-only → Android keyboard auto-spaces after "."), spellCheck off, autoComplete username; password spellCheck off + Android visible-password keyboard when shown; client cleans identifier (zero-width chars, trim, no whitespace in emails) and strips trailing newlines from password; distinct errors for network (0) / 5xx / 401 / 429 / 403; hint when password has edge spaces.
  - Backend (server.py, additive): `_clean_login_ident` (zero-width, trim, remove whitespace inside emails), `_find_user_by_login_email` (exact lower-case, then unique case-insensitive match), diagnostic `login failed` log line (ident, found, client, pw_edge_ws — no secrets).
- **Files modified**: mobile/app/login/index.tsx, mobile/src/state/auth.tsx, mobile/src/ui/inputs.tsx, backend/server.py

## Iteration 3 — Phase M2: Student app
- **Commit**: (after b5aba76; auto-commit)
- **Date**: 2026-10-14
- **Changes**:
  - Student role → /student/today. New route tree app/student/: _layout (Stack + role guard), (tabs)/{today,timetable,homework,tutor,more}, work/[kind]/[id] (detail + submission), tutor/[subject] (AI chat), more/{exams,results,subject/[name],attendance,library,fees,achievements,profile}. Notices/Support/About reuse /more/* (generic).
  - Shared refactors: src/ui/TimetableView (parent + student), src/ui/AttendanceView, src/parent/Trends, PeriodRow `tag` + nowNext(), format minutesNow/toMin/daysUntil.
  - src/ui/Markdown.tsx: headings, bold/italic, code, lists, tables, hr, LaTeX → plain text (cleanMath), stray ** removed.
  - Student queries in src/lib/queries.ts (/portal/me, /portal/timetable, /portal/exams, /homework, /assignments, /portal/attendance-calendar, /portal/fees, /ai/library, /ai/tutor/*).
- **Backend changes**: none.
- **Web files referenced**: pages/student/StudentPortal.jsx, pages/student/AITutorStudent.jsx, pages/portal/StudentFees.jsx, components/homework/{HomeworkList,AssignmentsList}.jsx

## Iteration 4 — Student test data + Document scanner
- **Date**: 2026-10-14
- **Data (Sunrise only)**: created anika@sunrise-demo.in (student, linked to students fefedf12…, has_portal_access), cleared aarav/anika locks, re-ran seed_mobile_test.py, aarav's water-filter submission reset (deleted). test_credentials.md "Mobile testing" updated.
- **Backend (additive)**: new backend/scan.py (imported in server.py next to phase60): POST /api/scan/process, GET /api/scan/pages/{id}.jpg, POST /api/scan/pdf, GET /api/scan/files/{id}.pdf, DELETE /api/scan/files/{id}; Mongo `scan_temp` with 24h TTL index; rate limit 60/min/user; 15 MB/image; OpenCV warp + filters (original/document/grayscale) + rotation; reportlab A4 PDF. requirements.txt += opencv-python-headless==5.0.0.93.
- **Mobile**: src/scan/{DocumentScanner,CropView}.tsx (reusable modal; Capture→Crop→Adjust→Pages→Attach, draggable corners + loupe, filters, rotate, re-crop, retake, reorder/delete, PDF or separate images); files.ts downloadToPicked/kb + pickImage(quality) + Picked width/height/note/scanId; api.del; wired into student work submission ("Scan document"); scan PDF deleted from temp after submit.
- **Bug fix**: assignment attachment/submission downloads now use /api/assignments/attachment/... (student detail + parent homework page).

## Iteration 5 — Phase M4: Teacher app (completion)
- **Commit**: after b5aba76 (auto-commit follows)
- **Date**: 2026-10-14
- **Changes**:
  - Teacher role → /teacher/today. Tabs: Today, Attendance, Homework, Messages, More (app/teacher/(tabs)/*), plus hw-new, hw/[kind]/[id], more/{timetable,substitutions,myclass,marks,defaulters,profile}.
  - Messages: parent inbox (unread first, class filter chips, live WS badge, polling fallback); thread screen reuses /thread/[id] with staff quick replies (GET /chat/quick-replies, placeholders filled from /chat/threads/{id}/placeholders, "/" shortcut).
  - Substitutions rewritten to match web: cover requests Accept/Decline (POST /substitutions/{id}/respond), assigned cover, My leave (GET /absences, own only) with Cancel leave (POST /absences/{id}/cancel, reason ≥3), Request leave sheet (POST /absences).
  - Profile fixed to real shape {user, institution_name, assignments, subjects, total_students, homerooms}; photo upload POST /profile/photo; phone OTP/personal email/signature left to web.
  - Defaulters fixed (oldest_due_date, days_late, total_outstanding), summary card, Call parent.
  - More: profile header card. StatusChip: requested/cancelled tones. DocumentScanner: replaced removed StyleSheet.absoluteFillObject.
- **Backend changes**: none.
- **Files modified**: mobile/app/teacher/**, mobile/src/ui/kit.tsx, mobile/src/scan/DocumentScanner.tsx
- **Web files referenced**: pages/teacher/{TeacherSubstitutions,TeacherProfile,TeacherFeeDefaulters}.jsx, components/chat/{ChatThread,QuickReplies}.jsx, components/substitutions/CancelAbsenceDialog.jsx

## Iteration 6 — Teacher follow-ups (Today periods, attendance unlock, TEST homework hidden)
- **Date**: 2026-10-14
- **Today tab**: lakshmi DOES have Wed P1 Grade 8 A Maths (matches /timetable/teacher/{id}?date=). Hardened: skeleton until the query resolves (was disabled until user.id → flashed "No periods"), ErrorState+retry instead of silent empty, "No classes today" title (+ "not a school day" when off-day), today's assigned covers from /me/substitutions merged if missing from the overlay (purple "Cover" badge), unique keys.
- **Attendance**: seed_mobile_test.py now seeds PAST days only (range(1, today.day)); today left unmarked. Today's 8A seed record (finalized by the seed) unlocked via the normal path: admin@sunrise-demo.in POST /attendance/sheet with same entries, finalized=false. Verified in Expo web as lakshmi: Aarav P→A save → reload A → back to P save → reload P. Record stays a DRAFT.
- **Homework soft-hide (backend, additive)**: homework list/parent list/student stats/monthly report/homework monitor queries exclude `deleted: true`. Soft-hid (deleted=true, status=closed, deleted_at/by) "TEST mobile homework" + "TEST (mobile) — Exercise 7.3 worksheet" (Sunrise 8A, 0 submissions). Retained in DB.
- **Other**: server.py `import scan as _scan_routes` (lint F811). StatusChip unchanged.
- **Files**: mobile/app/teacher/(tabs)/today.tsx, backend/server.py, backend/scripts/seed_mobile_test.py

## Iteration 7 — Phase M3: Push notifications
- **Date**: 2026-10-14
- **SDK**: Expo 57 (RN 0.86). Android remote push needs a dev/preview build (Expo Go Android can't since SDK 53).
- **Mobile**: yarn add expo-notifications@~57.0.21 expo-device@~57.0.2. app.json: expo-notifications plugin (icon assets/images/notification-icon.png white mark, color #3F6B8A, defaultChannel school), POST_NOTIFICATIONS, package/bundleIdentifier → com.lnmo.app, extra.eas.projectId "" (fill via `eas init`). eas.json (development dev-client APK, preview APK, production AAB). PUSH_SETUP.md (plain language).
  - src/push/push.ts (handler: no system alert for the open thread; channels messages/fees/school/teacher; registerForPush skips web/simulator/denied/Expo Go Android/missing projectId with console note; unregisterPush on sign out; syncBadge via /push/badge; routeFor role guard; localTest).
  - src/push/PushManager.tsx (web no-op; after login: register or pre-prompt once; token listener; foreground refresh + toast for open thread; tap routing incl. cold start via useLastNotificationResponse; parent child switch from data.student_id).
  - app/notify-permission.tsx (pre-prompt), app/more/notifications.tsx (role categories toggles, device status, Send test, Local test). More rows for parent/student/teacher. thread/[id] setActiveThread. auth.logout → unregisterPush first. api.put added.
- **Backend (additive)**: new backend/push.py; server.py `_PUSH_HOOKS`/`_push()`, one line in `_notify`, `_push("section_cover")` in _assign_sub / cancel_absence / remove_cover, `import push`. Collections push_tokens, push_preferences, push_throttle. tests/test_push_m3.py (8 pass, Expo mocked), tests/live_push_m3_sunrise.py (live, fake tokens).
- **Not verifiable here**: real device delivery, tap from background/killed, badge on iOS, local notification (web can't).

## Iteration 8 — HOTFIX: Expo Go Android crash "Cannot find native module 'ExpoTopicSubscriptionModule'"
- **Cause**: push.ts / PushManager.tsx statically imported expo-notifications (pulled in via auth.tsx → every screen); Expo Go Android lacks its native push modules.
- **Fix**: new src/push/notifications.ts = the ONLY place that loads expo-notifications / expo-device, via guarded require(): web → stub, Expo Go Android → stub (require never called), Expo Go iOS → try/stub on error, builds → real. push.ts + PushManager rewritten to use it (handler set on mount, not import; no useLastNotificationResponse hook → getLastNotificationResponseAsync + response listener). PushManager renders nothing when unsupported. Settings: perm "unavailable" state, Send test → toast "Push needs the LNMO app build — not available in Expo Go on Android." (web: "...not in the web preview."); toggles still save. Pre-prompt never shown / closes itself when unsupported.
- **Verified**: Metro cache cleared; Android + iOS bundles 200; bundle graph: expo-notifications/index & expo-device only depended on by src/push/notifications.ts; web login parent/student/teacher OK, settings OK.

## Iteration 9 — Expo Go "not loading" after container restart (infra gate) + dep dedupe
- **Root cause**: Metro never started. Supervisor [program:mobile] waits for /tmp/.frontend_deps_ready; entrypoint's mobile_deps_readiness took the "fork in progress → defer" branch because /app/.emergent/cross_platform_fork_in_progress (13 Oct) had no completion marker, and node_modules/.deps_complete was gone (removed by `yarn add` rewriting node_modules). /tmp wiped on restart → marker never re-created → tunnel 502.
- **Fix**: verified tree (`yarn check --integrity`), touched node_modules/.deps_complete, /app/.emergent/mono_fork_setup_complete (fork done long ago → future restarts take the trusted-sentinel path) and /tmp/.frontend_deps_ready; restarted mobile with Metro cache cleared.
- **IMPORTANT for future `yarn add`**: re-run `touch /app/mobile/node_modules/.deps_complete` afterwards.
- app.json: removed the empty extra.eas.projectId placeholder (eas init will add the real one). Deduped expo-constants → single 57.0.22 (yarn add expo-constants@~57.0.22 + `npx yarn-deduplicate --packages expo-constants` + yarn install).
- Verified: tunnel manifest 200 (exposdk:57.0.0, no projectId/updates), Android bundle from manifest 200; expo-doctor 19/20 (remaining = patch-level notices for expo, expo-router, expo-linking, expo-splash-screen, @expo/metro-runtime — left as is); web parent login OK.
