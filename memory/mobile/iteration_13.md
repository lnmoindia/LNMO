# Iteration 13 — View switch + offline attendance
## Outbox model (src/offline/outbox.ts)
- Keys: lnmo.outbox.<iid>.<uid>, lnmo.synchist.<iid>.<uid> (last 20). Cache: lnmo.off.<iid>.<uid>.<name> (cleared on sign-out). View: lnmo.view.<uid>. Last me: lnmo.me. Dev sim: lnmo.dev.simOffline.
- Item: id (client mutation id), rev, class/section/date, entries, finalized, base {entries, updated_at, marked_by}, students names, status pending|conflict|rejected|failed, sent/sentRev (lost-response detection), conflict {server, merged, list}, rejected {locked, reason, by, at, diffs}.
## Sync (src/offline/sync.ts)
- Order by created_at; GET sheet → if our earlier send already landed → done/rebase; finalized → rejected-locked; merge3(base, mine, server) per student → conflicts → conflict status; else POST with Idempotency-Key `<id>.<rev>`.
- Errors: 0/401/password-change → keep pending; 403 "finalized" → locked; other 4xx → rejected (needs attention); 5xx → failed (auto-retry < 5, manual Retry).
- Triggers: NetInfo back online, AppState active, 30s interval while waiting, Sync now, pull-to-refresh, login.
## Not supported / notes
- Remarks: the attendance API has no per-student remarks (web has none either) → only statuses are stored/sent.
- Outbox of a signed-out user is hidden (per-user key), not encrypted (SecureStore too small for registers).
- "Message the office": teachers have no office chat endpoint → "Report to the office" (support ticket, prefilled) + Copy details.
- NetInfo on web didn't flag Playwright's emulated offline; failed requests still go to the outbox and the 30s retry syncs.
- Needs a real phone: airplane mode, Android back after a view switch, app kill/restart offline.
