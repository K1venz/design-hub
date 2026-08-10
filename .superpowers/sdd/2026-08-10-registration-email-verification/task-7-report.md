# Task 7 — Two-step registration UI report

## Delivered

- Replaced the single-step registration completion path with an in-memory `details -> verification` flow.
- Added a progress indicator that reflects the actual sequence, masked pending-email copy, a six-digit ASCII-only code field, a 60-second resend cooldown, and a clear return-to-details action.
- The successful verification mutation continues to own session creation; the page observes the auth store and uses the existing post-login navigation behavior.
- Once the initial registration acknowledgement resolves, the page clears name, password, confirmation, agreement state, and source email. The verification state retains only a normalized lowercase pending email and the transient code input.
- Resend calls only `useResendRegistration({ email })`; it cannot receive profile or password state.
- Invalid or expired verification failures have a generic recovery message with explicit retry/resend directions. Resend failures likewise direct the user to retry or return to details.
- Extended Vitest's existing include expression to discover the required `.test.tsx` jsdom interaction test. No dependencies were added.

## TDD evidence

1. Added `image-web/src/pages/RegisterPage.test.tsx` before modifying `RegisterPage.tsx`.
2. Ran `npm test -- src/pages/RegisterPage.test.tsx` against the old page. It failed all five workflow tests because the old one-step page had no verification state or its new controls (first failure: missing accessible `昵称（选填）` label expected by the revised flow).
3. Implemented the minimum page state machine and reran the page test successfully.

The five interaction tests cover:

- details submit, normalized request payload, verification transition, and masked pending email;
- ASCII-only six-digit input plus successful authenticated navigation;
- disabled 60-second resend countdown, re-enable, and email-only resend payload;
- invalid/expired-code recovery and return to a form with password cleared;
- absence of the plaintext password and code from both localStorage and sessionStorage.

## Verification

All commands were run from `image-web`:

| Command | Result |
| --- | --- |
| `npm test -- src/pages/RegisterPage.test.tsx` | Pass — 1 file, 5 tests |
| `npm test` | Pass — 35 files, 198 tests |
| `npm run typecheck` | Pass |
| `npm run lint` | Pass |
| `npm run build` | Pass |

The build emits the pre-existing Vite warning about a minified JavaScript chunk exceeding 500 kB; it does not fail the build and is unrelated to this UI change.

## Visual and accessibility review

- Inspected the running `/register` page through Playwright at a 390×844 mobile viewport. The content is fully within the viewport: the layout removes the desktop panel, preserves a 285px usable form column, and exposes the progress sequence, fields, agreement checkbox, and disabled submit control without overlap.
- The accessibility snapshot confirms form labels for nickname, email, password, confirmation, agreement, progress list, and login link. The code field uses a label, `inputMode="numeric"`, `pattern="[0-9]*"`, one-time-code autocomplete, and error description linkage.
- Keyboard focus uses the existing `Input`/`Button` primitives. The new color transition explicitly disables under reduced motion. No new decorative gradients or autonomous animations were introduced.
