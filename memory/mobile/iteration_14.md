# Iteration 14 — Phase 61 mobile
Verified on the Expo web preview (Sunrise):
- A: 4000×3000 JPEG → ~250 KB upload (chat), progress pill + pending bubble; simulated 413 → error path (text + file restored); self photo upload/remove; scanner page processed + PDF resubmission. Release export (`npx expo export --platform android --no-bytecode`; hermesc can't run on this aarch64 box) → bundle calls resolveBackend(!1) → https://lnmo-fees.emergent.host.
- B: parent.menon Home "Lakshmi Menon · Class teacher · Grade 8 A" with photo, Message → existing thread; Child profile class + subject teachers.
- C: mobile.parent Ishaan → 1 thread, Anika → empty state; switcher photos.
- D: two sessions LIVE: 3 API msgs teacher→parent in 0.2s; 3 parent app→teacher, 3 teacher app→parent instantly; no dupes/pending.
- E: avatars on all dashboards, register rows (after backend sheet change), chat, timetable.
- F: lakshmi board (chips w/ counts, late filter) → detail (inline image, zoom viewer) → redo (feedback required) → aarav sees redo + due, resubmits with a scanned PDF (Attempt 2, earlier versions 1) → lakshmi reviews (prev attempt expandable) → parent sees Reviewed + Version 2; thomas board via More → Homework & assignments.
- Regression: all role logins, offline attendance save→sync, sindhu view switch.
Needs a real phone / production: Android release multipart (content:// from gallery, file:// from manipulator), upload progress events on device, production WS relay across replicas after redeploy, pinch-zoom (iOS) / tap-zoom (Android), push deep links for redo/reviewed.
