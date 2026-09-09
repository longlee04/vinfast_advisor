# Conversation Memory

## Contract

Conversation Memory is server-backed Agent state for one authenticated customer. The public identifier is `conversation_id`; during this MVP it maps one-to-one to `conversation_sessions.session_id`.

PostgreSQL is the only durable source of truth. LangGraph checkpointing, vector memory and cross-conversation profile memory are intentionally not used.

Customer routes are registered below `/api/v1`:

- `POST /conversations`
- `GET /conversations`
- `GET /conversations/{conversation_id}`
- `GET /conversations/{conversation_id}/messages`
- `POST /conversations/{conversation_id}/archive`
- `DELETE /conversations/{conversation_id}`
- `POST /conversations/{conversation_id}/turns`
- `GET /conversations/{conversation_id}/turns/{client_turn_id}`

Authentication is the only source of `customer_id`. Conversation request bodies never accept a user identity.

The pre-existing `/api/v1/agent/turn` contract remains available until all consumers have been inventoried and removal is approved as a separate public-contract change.

## Stored state

Agent migrations add:

- `conversation_sessions.archived_at` for user-controlled archive;
- `conversation_messages` for chronological customer-visible `USER` and final `ASSISTANT` messages;
- `conversation_summaries` for current summary, watermark, prompt version and model metadata;
- `conversation_turn_outcomes` for idempotent claim, exact replay and recovery state.

Existing `conversation_slots` and `pending_feature_mentions` remain the only structured slot and pending-feature stores.

Archive hides a conversation from the default list but preserves owner-readable detail. Delete hard-deletes the Agent conversation row and cascades Agent-owned memory. Any new audit or legal-retention table must make its retain/anonymize/cascade policy explicit before release.

## Turn transaction sequence

One turn is not wrapped in a long database transaction:

1. Transaction A verifies ownership and active state, locks the conversation, claims `(conversation_id, client_turn_id)`, allocates server turn order and appends the sanitized `USER` message.
2. The graph and its LLM/tool calls run without an open database transaction.
3. Transaction B persists the exact outcome, changed slots and a direct final `ASSISTANT` message atomically.
4. If advisor review is required, Transaction B records `WAITING_REVIEW` and the review ID but does not persist the advisor draft or waiting text as an assistant transcript message.
5. Summary runs best-effort after a completed visible pair and persists in Transaction C.

Graph failure records a safe immutable `FAILED` outcome and no synthetic assistant message or partial slot update.

## Idempotency and retry

Every new Conversation API turn requires a UUID `client_turn_id`.

- A transport retry caused by timeout or a lost response reuses the same key.
- `COMPLETED`, `WAITING_REVIEW`, `REJECTED` and other terminal states replay durable state without rerunning the graph.
- `IN_PROGRESS` returns a stable conflict response.
- `FAILED` is immutable; the same key returns the prior failure. A user-triggered new attempt must use a new key.

Message dedupe and turn idempotency are separate:

- messages use `(session_id, client_turn_id, role)` when a client key is present;
- turn outcomes use `(session_id, client_turn_id)` and `(session_id, turn_number)`.

The recovery GET route is authoritative after a missed HTTP or SSE response.

## Working Memory

Working Memory contains only data from the owned conversation:

- exact current slots;
- current summary;
- pending feature mentions;
- bounded recent visible messages with preserved USER/ASSISTANT roles;
- the current user message.

The domain projection is transport-neutral. Only the LLM adapter converts it to LangChain `SystemMessage`, `HumanMessage` and `AIMessage` objects. Completed message pairs are dropped oldest-first when the budget is exceeded; current slots and current user input remain authoritative.

## Summary behavior

Summary input contains only sanitized customer-visible transcript content. Advisor drafts are excluded.

The summary stores `summarized_through_turn`, prompt version and model name. Timeout, invalid output or provider failure does not roll back the response, transcript, outcome or slots. The old watermark remains, and a later successful summary includes unsummarized messages after that watermark.

## Human review delivery

Approval/edit follows commit-before-publish ordering:

1. resolve the review;
2. append exactly one final assistant message correlated by `review_id`;
3. advance the turn outcome and store the durable message ID;
4. commit;
5. publish an SSE event containing event, conversation/session, review, client-turn and message correlation IDs.

The customer delivery read path never creates transcript content. Missed SSE events recover through durable REST state. Rejection advances the outcome to `REJECTED`, publishes a terminal event and does not create an assistant message. `ReviewOperations.expire` provides the same atomic transition to `EXPIRED` for an external expiry policy or scheduler; this MVP does not invent a retention duration or background scheduler.

## Privacy and logging

Credential-shaped text is redacted before persistence, prompt projection and summary input. Application logs and HTTP errors may contain IDs, statuses, durations and safe error categories, but not raw transcript, tokens, cookies, database URLs or provider exception text.

Redaction must preserve normal Vietnamese vehicle, budget and usage requirements.

## Migration integration note

On `feature/build-agent`, Conversation Memory uses revisions `agent_0013` and
`agent_0014` after the build-agent migrations through `agent_0012`. Revision
`agent_0015` repairs databases that previously deployed the older memory chain
with colliding revision IDs, without dropping existing transcript data.

Do not merge the two histories without an explicit Alembic merge revision and a verified single head. Do not rename either history back to a revision ID already used by the other branch.

## MVP exclusions

- Cross-conversation user profile memory
- Embedding/vector retrieval for conversation history
- LangGraph checkpoint persistence
- Shared conversations or exports
- Retention TTL/background deletion
- Multi-process durable event broker
- Automatic rerun of immutable failed idempotency keys
