# Frontend Instructions — VinFast AI Sales Advisor UI Demo

## Scope

This frontend is a visual, interactive prototype only.

Build:
- Next.js/React UI
- TypeScript
- Tailwind CSS
- responsive layouts
- local mock data
- simulated interactions and states
- optional VinFast 3D vehicle viewer when an authorized asset is available

Do not build or modify:
- backend services
- APIs
- PostgreSQL or any database
- migrations
- authentication server
- JWT
- LangGraph
- RAG
- embeddings
- production integrations

Do not edit unrelated backend files.

## Customer UI rules

Customer-facing pages must not use:
- a permanent left sidebar
- a permanent right sidebar
- a full-height vertical step menu
- a narrow chatbot column beside the vehicle
- a fixed column containing all needs or vehicle controls

Use:
- compact top navigation
- centered primary content
- horizontal progress
- expandable summaries
- contextual modal, drawer, popover, or bottom sheet
- a compact bottom vehicle-control tray
- one main decision per screen

The vehicle, current question, recommendation, comparison, or booking action must remain the visual focus.

Advisor and Admin demo pages may use an operational sidebar.

## UI architecture

- Use strict TypeScript.
- Avoid `any`.
- Keep mock data outside page components.
- Keep calculations outside JSX.
- Use reusable components.
- Preserve the existing package manager and project conventions.
- Use Vietnamese for visible UI copy.

Suggested mock-data location:

```text
frontend/src/mocks/
```

Suggested local demo store:

```text
frontend/src/store/demo-store.ts
```

## VinFast assets

- Do not use a generic vehicle and label it VinFast.
- Do not scrape or download unofficial 3D models.
- Use only supplied or authorized VinFast assets.
- When no valid 3D asset exists, use an authorized VinFast poster image and show a clear 3D-pending message.
- The displayed model name must match the loaded asset.

Suggested asset paths:

```text
frontend/public/models/vinfast/
frontend/public/images/vinfast/
```

## Visual quality

- Follow `DESIGN.md`.
- Keep the experience simple, modern, premium, and product-first.
- Use strong whitespace and restrained blue accents.
- Avoid excessive gradients, shadows, glassmorphism, glowing cards, and decorative animation.
- Do not make customer pages look like admin dashboards.

## Verification

Run the repository's frontend equivalents of:

```bash
npm run lint
npm run typecheck
npm run build
```

Report actual results. Do not claim success without running the commands.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
