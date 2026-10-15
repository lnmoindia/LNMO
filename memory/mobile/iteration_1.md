# Mobile iteration 1 (Phase M1)

## Structure
- app/_layout.tsx (fonts Outfit+Figtree, Auth/Child/Toast providers, SessionGuard), app/index.tsx (splash + redirect)
- app/school.tsx, app/login/index.tsx, app/login/[code].tsx (deep link), app/change-password.tsx, app/setup/parent/[token].tsx, app/unsupported.tsx (non-parent roles)
- app/(parent)/_layout.tsx tabs: home, timetable, fees, messages, more
- Stack screens: invoice/[id], proof/[id], issue/[id], thread/[id], new-message, more/{homework,attendance,results,notices,achievements,profile,account,link-child,support,about}
- src/lib: api.ts (fetch + Bearer + refresh + events), chat.ts (WS), files.ts (picker, FormData, authed download+share), format.ts (₹ en-IN, tz dates, IST default; tz updated from chat responses), queries.ts (react-query hooks)
- src/state: auth.tsx (school/user/brand, brand cached in storage), brand.ts (palette from primary_color, fallback #3F6B8A), child.tsx (selected child persisted), toast.tsx
- src/ui: kit.tsx, inputs.tsx, Screen.tsx (TabScreen/StackScreen, pull-to-refresh, offline banner), brandbits.tsx, ChildSwitcher.tsx, PhotoPicker.tsx
- src/parent: timetable.tsx (cover badges), alerts.ts (Today strip rules), NoticeCard.tsx, LiveBadge.tsx

## Endpoints used (same as web)
/auth/login, /auth/me, /auth/logout, /auth/refresh, /auth/change-password, /me/branding, /public/institutions/{code}/branding,
/public/parent-setup/{token}, /parent/children, /parent/child/{sid}[/timetable|/homework|/assignments|/fees|/exams|/attendance-calendar|/fees/statement.pdf],
/notices/feed, /notices/attachment/{id}/{i}, /fees/invoices/{id}/pay-info, /parent/fees/invoices/{id}/proofs, /parent/fees/invoices/{id}/issues,
/parent/fees/issues/{id}/messages, /fees/payments/{pid}/receipt.pdf, /chat/threads, /chat/threads/{id}, /chat/threads/{id}/messages,
/chat/messages/{mid}/attachment, /chat/unread, /verify/request, /verify/confirm, /parent/unlink/{sid}, /support/issues, /homework/attachment/{id}/{i}, ws /api/ws/chat?token=

## Deps added (yarn expo install)
expo-image-picker, expo-sharing, expo-document-picker, @expo/vector-icons, @react-native-community/netinfo, expo-clipboard, expo-file-system, @expo-google-fonts/outfit, @expo-google-fonts/figtree

## Verified (Expo web preview)
School code (wrong → "School not found"), branded login, wrong password, lockout 429 msg, Home, Timetable today/week, Fees + statement PDF download, invoice QR, proof upload (Term 3 → pending), Messages live WS (typing + live receive with lakshmi@), send text + image, More pages, forced change-password + child switcher (temp parent in TEST school, deleted), sign-out, reload persistence, change school.

## Not verified / deferred
- Native Expo Go device run (Android bundle compiles), camera, share sheet, upi:// open, hardware back, pull-to-refresh gesture, offline banner.
- Substitute badges (no substitutions in data today). Setup-link deep link (no fresh token). Dark mode not implemented (optional).
- Test data left: a pending ₹500 proof on Aarav's Term 3 invoice; chat messages in thread 5b52628e (QA check).
