"""Behavioral checks for the rendered Docker Compose deployment model."""

import json
import os
import shutil
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _render_compose_config() -> dict[str, object]:
    docker = shutil.which("docker")
    assert docker is not None, "Docker CLI is required for Compose deployment tests"

    environment = os.environ.copy()
    environment.update(
        {
            "POSTGRES_USER": "compose_test",
            "POSTGRES_PASSWORD": "compose_test_secret",
            "POSTGRES_DB": "compose_test",
            "PGADMIN_DEFAULT_EMAIL": "compose@example.com",
            "PGADMIN_DEFAULT_PASSWORD": "compose_test_secret",
        }
    )
    result = subprocess.run(
        [
            docker,
            "compose",
            "config",
            "--no-env-resolution",
            "--format",
            "json",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_compose_wires_healthy_frontend_to_backend() -> None:
    config = _render_compose_config()
    services = config["services"]
    assert isinstance(services, dict)

    frontend = services["frontend"]
    assert frontend["build"]["args"] == {
        "NEXT_PUBLIC_API_BASE_URL": "http://localhost:8000/api/v1",
        "NEXT_PUBLIC_DEMO_MODE": "false",
    }
    car_pdf_context = frontend["build"]["additional_contexts"]["car_pdf"]
    assert Path(car_pdf_context) == REPOSITORY_ROOT / "data-p150" / "car_pdf"
    assert frontend["ports"] == [
        {
            "mode": "ingress",
            "target": 3000,
            "published": "3000",
            "protocol": "tcp",
        }
    ]
    assert frontend["depends_on"]["backend"]["condition"] == "service_healthy"
    assert frontend["restart"] == "unless-stopped"
    healthcheck = " ".join(frontend["healthcheck"]["test"])
    assert "http://localhost:3000" in healthcheck
