from pathlib import Path


def test_startup_code_never_dumps_database_url_environment_values() -> None:
    main = Path("src/main.py").read_text(encoding="utf-8")

    assert "_log_database_urls()" not in main
    assert 'print(f"{key}={val}")' not in main

    entrypoint_path = Path("docker-entrypoint.sh")
    if entrypoint_path.exists():
        entrypoint = entrypoint_path.read_text(encoding="utf-8")
        assert 'env | grep "_DATABASE_URL"' not in entrypoint
