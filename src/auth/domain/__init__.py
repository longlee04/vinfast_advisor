"""Auth domain layer.

Framework-independent entities, value objects, and policies. This package must
not import FastAPI, SQLAlchemy, Alembic, SendGrid, or any concrete adapter, and
must not read configuration or the wall clock (`AGENTS.md:26-27`).
"""
