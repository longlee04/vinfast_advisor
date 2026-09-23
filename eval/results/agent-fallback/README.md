# Ket qua danh gia agent fallback

Chay bang `scripts/agent_eval.py` (plan agent-migration Buoc 9):

```
uv run python -m scripts.agent_eval \
  --base http://127.0.0.1:18000/api/v1 \
  --email <email> --password <mk> \
  --dsn "$AGENT_DATABASE_URL" \
  --out eval/results/agent-fallback/latest.md
```

Moi lan chay ghi mot cap `<stamp>.md` + `<stamp>.json`. Script tu tra co ve TAT
sau vong ON. Ngoai ra doc chi so tu `turn_traces`:

```
uv run python -m scripts.core_v2_metrics --days 1 --core v2
```

`baseline-unit.txt` / `baseline-integration.txt` la moc test truoc khi bat dau
plan (2026-09-22).
