# Unified Chat Model Selector Design

## Goal

Replace the standalone image-model selector at the top of Chat with one compact model entry beside the send button. The entry lets a user choose both the text model used by Chat and the image model used by generation, while keeping the composer familiar and uncluttered.

The interaction follows DeerFlow's established composer pattern: current model shown in a compact trigger, model selection adjacent to send, searchable model list, secondary upstream identifier, and an explicit selected state. Our product keeps a dropdown instead of a modal and adds a second model category because Chat coordinates both text and image generation.

## Scope

- Add an interactive demo page with three visual variants before choosing the production styling.
- Add a public catalog for enabled and verified Chat models.
- Let Chat requests explicitly select a text model.
- Keep the existing account-scoped image-model selection shared by all image tools.
- Store the account-scoped Chat-model selection in browser storage.
- Move model selection into the Chat composer and remove the current top-of-page image selector.
- Bundle the known provider logos locally. Unknown providers use an intentional neutral model icon.

## Non-goals

- Pricing, wallet balances, tokens, or estimated cost.
- Model parameters such as temperature, reasoning effort, or output quality.
- A new settings page or full-screen model-management dialog.
- Changing administrator model-configuration behavior.
- Changing the standalone reverse-prompt tool to use a user-selected Chat model.

## Demo variants

The local-only demo route presents the same data and behavior in three styles:

1. **DeerFlow minimal** — compact text-model trigger immediately left of send; image-model logo appears as a small secondary mark; the dropdown uses dense two-line rows.
2. **Brand cards** — the same trigger opens more spacious branded rows with stronger provider color and category separation.
3. **Dual-model compact** — one trigger visibly contains two compact segments for the active text and image models, while still opening one shared dropdown.

All variants support search, two model groups, immediate selection, selected checks, disabled/busy state, and responsive truncation. The demo uses static fixtures and cannot call model APIs.

## Composer interaction

- Place the trigger in the composer footer immediately before the send button.
- The trigger shows the selected Chat model's local brand logo and display name.
- A smaller image-model logo communicates that the same entry also controls image generation.
- Open the dropdown upward so it remains attached to the composer.
- Put a search field at the top and group results under `文本模型` and `图片模型`.
- Each row contains a local brand logo, display name, upstream/internal model identifier, and a check for the selected item.
- Selecting a row takes effect immediately, persists the selection, closes the dropdown, and returns focus to the composer.
- Lock the trigger while a response or generation confirmation is active. A changed model applies to the next message only.
- Never clear draft text, attachments, or the selected edit source when selection changes or catalog loading fails.

## Model availability

Only enabled, verified models with a current connection fingerprint appear in a public catalog. The server default is used only for first-time initialization. If a stored model disappears from the catalog, the selection becomes explicitly required; the application does not silently switch to another model.

The selector handles text and image catalog states independently. Loading and error feedback remains inside the dropdown. Chat submission stays disabled until both required selections are valid because every Chat turn may invoke image-generation tools.

## API and runtime behavior

- Generalize the existing image catalog response into one common catalog-item shape without changing the current `/models/image` response fields.
- Add `GET /models/chat` for enabled and verified Chat models.
- Add `chat_model` to `POST /chat/messages` and pass the chosen identifier through the Chat orchestrator.
- Change text-model resolution from default-only resolution to explicit model-ID resolution.
- Store the selected Chat model on a pending generation action so the confirmation response uses the same text model as the turn that created it.
- Keep services without a user-facing Chat selector, including the standalone reverse-prompt endpoint, on the administrator-configured default text model.
- Return the existing model-unavailable business error when a model is disabled or changed after catalog loading. The frontend preserves the user's composer state and requires reselection.

## Frontend state

Use one generic account-scoped model-selection mechanism for both model types rather than duplicating the current image store. Storage keys are namespaced by user ID and model type. Each selection reconciles against its own catalog and remembers whether explicit reselection is required.

The global image selection remains available to every image tool. Chat owns the Chat-model selection because it is the only current user-facing text-model consumer.

## Brand presentation

The initial known brands are DeepSeek, Doubao, OpenAI, and Wan. Assets are stored in the frontend bundle to avoid runtime dependency on a third-party logo service. Brand detection is presentation-only and maps known configured model identifiers to assets; an unrecognized, otherwise valid model is rendered with the neutral model glyph and remains fully usable.

## Accessibility and responsive behavior

- Trigger and rows are keyboard reachable and expose current selection to assistive technology.
- Search filters both groups and preserves keyboard navigation.
- The dropdown width is capped on desktop and constrained to the mobile viewport.
- Long display names and identifiers truncate without increasing composer height.
- Selected state is conveyed by both a check and accessible text, not color alone.

## Verification

- Backend unit tests cover filtered Chat catalogs, explicit resolver selection, wrong-type/disabled model rejection, request schema, and pending-confirmation model consistency.
- Frontend unit tests cover catalog reconciliation, account isolation, search, grouped selection, missing-model behavior, busy locking, and request-body construction.
- The demo page is manually checked at desktop and mobile widths before one style is promoted into Chat.
- Focused backend and frontend tests run during development; a frontend production build verifies the final integration.

