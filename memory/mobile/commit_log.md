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

## Iteration 10 — Build readiness for Emergent Publish → Mobile → Android
- **eas.json REMOVED**: no template eas.json ever existed (mobile/ first committed in 180ee87 already with our M3 file; it was created by us via create_file in M3). Emergent manages EAS; no projectId/owner/updates added.
- **app.json**: name LNMO, slug "mobile" (template, unchanged), version 1.0.0, android.versionCode 1, package/bundleIdentifier com.lnmo.app; adaptiveIcon + new monochromeImage (assets/images/adaptive-monochrome.png, 1024, white mark); permissions CAMERA, READ_MEDIA_IMAGES, POST_NOTIFICATIONS, INTERNET, VIBRATE; blockedPermissions RECORD_AUDIO, READ_MEDIA_VIDEO/AUDIO, WRITE_EXTERNAL_STORAGE, location, READ_CONTACTS, SYSTEM_ALERT_WINDOW; image-picker microphonePermission false + new camera/photo strings (also iOS infoPlist); removed preview-host https intentFilters + iOS associatedDomains (lnmo:// scheme kept); expo-notifications plugin kept; NO googleServicesFile (file not present).
- **api.ts**: BACKEND normalised (trim, strip trailing "/" and "/api") + warn if unset. No hardcoded URLs anywhere.
- **Deps**: expo 57.0.29, expo-router ~57.0.27, expo-linking ~57.0.13, expo-splash-screen ~57.0.10, @expo/metro-runtime ~57.0.17. expo-doctor 20/20, expo install --check up to date. Sentinel re-touched.
- **Proof**: prebuild (temp copy) OK → applicationId com.lnmo.app, versionCode 1, merged perms as intended, monochrome + notification icon + white splash; `expo export --platform android --no-bytecode` OK (hermesc local = x86 vs aarch64 container, irrelevant for cloud build). .gitignore: /android, /ios.
- PUSH_SETUP.md rewritten for the Emergent Publish flow.

## Iteration 11 — Release builds always use the production backend
- app.json expo.extra.productionBackendUrl = https://lnmo-fees.emergent.host (no EAS fields, no eas.json).
- src/lib/api.ts: resolveBackend(__DEV__): dev → EXPO_PUBLIC_BACKEND_URL (preview, from .env, unchanged); release → extra.productionBackendUrl (Constants.expoConfig, with app.json require() fallback inlined in the JS bundle) → env only if missing. Normalised (trailing / and /api). BACKEND_HOST exported. REST (API), absUrl (assets/PDF/branding) and chat WS (chat.ts) all build on BACKEND.
- About: "Version 1.0.0 (dev)" + "Server: <host>" (testIDs about-version, about-backend-host).
- Verified: prod export bundle has `l=c(!1)` → production host; web preview parent login uses only the preview host; About shows preview host in dev.
- LIVE (https://lnmo-fees.emergent.host): /api/ 200 "LNMO API ok", but OLD code — missing /api/push/* (5) and /api/scan/* (5) → user must Redeploy. Production DB has none of sunrise/lpgs/p50demo (branding 404) — separate DB from preview.

## Iteration 12 — Phase M6: Principal app
- **Commit**: be048ac (base; M6 files currently uncommitted in working tree — auto-commit pending)
- **Date**: 2026-10-15
- **Changes**:
  - Routing: index.tsx → `/principal/today` when `user.role === "teacher" && user.is_principal`. app/principal/_layout.tsx + (tabs)/_layout.tsx (Today, Cover, Attendance, Fees, More).
  - Today: division attendance, teachers absent, periods needing cover, day-book total, pending proofs/issues, unread parent msgs, exams.
  - Cover: day picker, mark teacher absent, substitute suggestions, assign/ask/auto-cover/cancel/remove.
  - Attendance: division-scoped class list → att.tsx register (shared src/ui/AttendanceRegister.tsx, also used by teacher attendance tab).
  - Fees: Day Book, Defaulters, Proofs (approve/reject), Issues. Counter collection NOT built (note shown: stays on web).
  - More: messages, students (+student/[id]), teachers (+teacher/[id]), notices (create with scanner), users (ResetSheet unlock/reset), teacher view, profile, notifications, support, about.
  - src/principal/hooks.ts, src/principal/ResetSheet.tsx.
  - Lint: removed eslint-disable comments for rule `react-hooks/set-state-in-effect` (not defined in config) in fees.tsx + AttendanceRegister.tsx.
- **Verified**: lint clean; web preview login sindhu@sunrise-demo.in → all 5 tabs render, scoped to Grade 5 A only.
- **Files**: mobile/app/index.tsx, mobile/app/principal/**, mobile/src/principal/**, mobile/src/ui/AttendanceRegister.tsx, mobile/app/teacher/(tabs)/attendance.tsx

## Iteration 13 — Principal ⇄ Teacher view switch + offline attendance (Phase M5)
- **Commit**: be048ac (base; changes uncommitted in working tree — auto-commit pending)
- **Date**: 2026-10-15
- **Task 1 (view switch)**: src/state/view.ts (lnmo.view.<uid>, default principal, switchView = dismissAll + replace → first tab), src/ui/ViewSwitch.tsx (ViewSwitch segmented, ViewPill header). Principal More top segmented pill (old "Teacher view" row removed), Principal Today header pill "Teacher view"; Teacher More top row "Switch to Principal view" + Teacher Today header pill — principals only. index.tsx restores the saved view. StackScreen back fallback → homeFor(user).
- **Task 2 (offline attendance)**: src/offline/{cache,net,outbox,sync,prefetch,OfflineSync,SyncBanner,warn}.ts(x); app/offline/index.tsx (More → Offline sync: status, Sync now, Refresh offline data, Needs attention, Waiting, history 20, dev "Simulate offline" switch) and app/offline/[id].tsx (Resolve sync conflict / Not applied (locked) with diffs, Report to the office → /more/support prefilled, Copy details, Dismiss / Waiting + Discard).
  - queries.ts: useMyClass/useTeachingOptions/useTeacherTT/useAttendanceSheet → cachedGet (network first, per-user AsyncStorage fallback on status 0) + networkMode "always".
  - AttendanceRegister: saveRegister() (online → POST as before with Idempotency-Key; offline / network error → outbox), pending marks override server data, "Saved offline — will sync" strip, " · offline" chip suffix.
  - api.ts: Opts.headers, api.post(p, body, headers), netSim + simReady (dev-only simulated offline). BACKEND resolver untouched.
  - auth.tsx: applyUser() sets cache owner + stores lnmo.me (offline cold start keeps the session on network error); logout clears lnmo.off.* (outbox kept per user, hidden). Sign-out warning with unsynced count (teacher + principal More).
  - Screen.tsx: OfflineBanner uses useOnline (NetInfo + sim), SyncBanner on every screen, TabScreen `right` slot, pull-to-refresh also prefetches + syncs.
  - support.tsx: optional params title/desc.
- **Backend (additive)**: POST /api/attendance/sheet accepts optional `Idempotency-Key` header (per user, scope attendance_sheet, 24h TTL in new `idempotency_keys` collection; replay returns the stored result + `Idempotent-Replay: true`). Save logic moved verbatim into `_save_attendance_sheet`. Startup index `_idempotency_indexes`.
- **Verified (web preview)**: lakshmi 8A offline 2 absent → reload → pending → online → synced; conflict (admin Late vs mine Absent) → conflict screen → pick → saved, admin's other change kept; locked (admin finalize) → rejected-locked, no overwrite; real fetch failure (Playwright offline) → outbox → auto-sync via 30s interval; different user (rahul) doesn't see/send lakshmi's outbox, lakshmi re-login syncs it; sindhu switch both ways + remembered; parent/student/teacher/principal logins OK. Android bundle 200. 8A 14+15 Oct restored from /app/tests/backup_8A_attendance.json (exact).

## Iteration 14 — Phase 61 (mobile): uploads, class teacher, chat-by-child, live chat fix, photos, submissions/redo
- **Commit**: base ed7be74 (changes uncommitted in working tree — auto-commit pending)
- **Date**: 2026-10-15
- **A Uploads**: api.ts `uploadForm` (XHR, Bearer, 90s timeout, progress store, 1 retry on a dropped connection, 401 refresh); `api.postForm` routes through it. Error mapping `failure()`: 413 → "File too large (max N MB)", 503 → scanner/service unavailable, 5xx → "Server error, try again", timeout → "Upload is taking too long…"; "offline" wording only when NetInfo says offline (`netState`, set by offline/net.ts). files.ts: `prepareImage` (expo-image-manipulator: ≤2000px, JPEG 0.75; scanner ≤3000; square crop for avatars), `appendFile` downscales + content:// → cache copy + {uri,name,type}; `tooBig` (PDF-only size checks). src/ui/UploadProgress.tsx in root layout. Dependency: expo-image-manipulator ~57.0.21.
- **B**: src/parent/ClassTeacherCard.tsx (card + SubjectTeachers + messageClassTeacher → existing open thread or /new-message?child&target). Home + Child profile (also guarded cold-load crash). new-message accepts params.
- **C**: useThreads(poll, studentId) → /chat/threads?student_id; useUnreadBy (/chat/unread by_student) → ChildSwitcher dot + per-child badges.
- **D**: chat.ts useChatSocket ref-based (subscribe once per mount), "reconnected" synthetic event, waits for the token on cold start (was the real cause of "CONNECTING…" when a thread is opened directly). thread/[id]: serialized pull + mergeThread (de-dup by message id, temps reconciled), optimistic temp bubbles swapped by temp id, restore text/file on failure, sender avatars + participants.
- **E**: Avatar(uri) w/ initials fallback; student/teacher/principal Today headers, child card/switcher, register rows, principal student list/detail, chat, timetable teacher. src/ui/MyPhoto.tsx (MyPhotoCard POST/DELETE /photos/me; StudentPhotoButton POST /photos/students/{sid}, hidden on 403) in teacher profile, student profile, parent My account.
- **F**: src/work/SubmissionBits.tsx (STATE chips, AuthedImage, zoom Viewer, Attachments, Attempt); teacher/hw/[kind]/[id] = Submissions board (filters with counts); app/submission/[kind]/[id] detail (review w/ marks, redo w/ feedback + due chips, previous attempts); app/principal/work.tsx (More → Homework & assignments); student detail: redo banner, Attempt + earlier versions, Resubmit; parent homework: Reviewed/Redo requested/version; filterWork treats redo as due.
- **Backend (additive)**: push.py `_route` also deep-links homework/assignment _redo/_verified; server.py GET /attendance/sheet adds photo_url/thumb_url to students (phase61.add_photos).
- **Verified (web preview)**: see iteration_14.md. Test data cleaned (TEST submission, 6 notifications, 16 test chat messages, parent.menon photo removed, 8A 14 Oct restored).
