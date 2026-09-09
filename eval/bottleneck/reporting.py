"""Safe JSON reporting for bottleneck evaluation."""

from eval.bottleneck.models import EvalReport


def render_json(report: EvalReport) -> str:
    """Serialize aggregate-only report; case text and provider traces never enter model."""
    return report.model_dump_json(indent=2)
