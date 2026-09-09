# Conversation Memory Runbook

## Preconditions

- Python 3.11+
- Project PostgreSQL/pgvector service reachable
- Agent database URL targets a disposable database for migration/integration tests
- Automated tests use fake Agent/Summary LLM adapters and do not call paid providers

Do not print database URLs or `.env` values into CI logs.

## Migration verification

Always select the Agent Alembic configuration explicitly:

```powershell
python -m alembic -c alembic-agent.ini heads
python -m alembic -c alembic-agent.ini upgrade head
python -m alembic -c alembic-agent.ini downgrade base
python -m alembic -c alembic-agent.ini upgrade head
```

Approve only when there is one intended head and SQLAlchemy metadata parity tests pass. When integrating `feature/build-agent-long`, create and verify an explicit merge revision because its `agent_0012` head and the Conversation Memory branch history are independent.

## Focused verification

```powershell
ruff check src/agents migrations/agents tests/agents
pytest tests/agents/unit -v --tb=short
pytest tests/agents/integration/test_migrations.py -v --tb=short
pytest tests/agents/integration/test_conversation_repository.py -v --tb=short
pytest tests/agents/integration/test_conversation_memory_repository.py -v --tb=short
pytest tests/agents/integration/test_conversation_lifecycle_repository.py -v --tb=short
pytest tests/agents/integration/test_conversation_api.py -v --tb=short
pytest tests/agents/integration/test_review_actions.py -v --tb=short
pytest tests/agents/integration/test_turn_events_sse.py -v --tb=short
```

Final project gates remain:

```powershell
ruff check src/ tests/
pytest tests/ -v --tb=short
```

Record unrelated pre-existing failures separately. Do not suppress or repair them as part of Conversation Memory.

## Manual API smoke test

As an authenticated customer:

1. Create two conversations.
2. List and switch between them; verify no transcript crosses conversations.
3. Submit a turn with a new `client_turn_id`.
4. Repeat the identical request with the same key; verify exact replay and no duplicate message.
5. Reload messages and recover the turn through the GET outcome route.
6. Archive one conversation; verify it is hidden from the default list and remains owner-readable.
7. Attempt read/write with another account; verify the privacy-safe not-found contract.
8. Delete the conversation; verify its Agent memory is gone.

For reviewed turns, verify approve/edit commits the final message before SSE, reconnect recovers through REST, and reject or an explicit `ReviewOperations.expire` call exits waiting state without exposing a draft. Automatic expiry scheduling remains outside this MVP.

## Summary degradation

A summary provider timeout is non-fatal. The expected operational state is:

- turn outcome and visible transcript committed;
- slots committed;
- old summary watermark retained;
- no raw provider error or transcript logged;
- the next successful summary catches up unsummarized messages.

Escalate only if transcript/outcome persistence fails or the watermark moves past messages that were not summarized.
