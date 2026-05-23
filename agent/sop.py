import json
from pathlib import Path


def load_sop(path: str = "data/sop.json") -> dict:
    sop_path = Path(path)
    if not sop_path.is_absolute():
        sop_path = Path(__file__).resolve().parents[1] / sop_path

    with open(sop_path, "r", encoding="utf-8") as f:
        return json.load(f)


def sop_to_text(sop: dict) -> str:
    """Convert SOP dict to a clean structured text block for injection into system prompts."""
    s = sop
    hours = s["hours"]
    services = "\n".join(
        f"  - {sv['name']}: from £{sv['price_from']} ({sv['notes']})"
        for sv in s["services"]
    )
    triggers = "\n".join(f"  - {t}" for t in s["escalation_triggers"])
    return f"""BUSINESS: {s['business']['name']} ({s['business']['type']})
HOURS: {hours['days']}, {hours['open']} – {hours['close']}. Closed {', '.join(hours['closed_days'])}.
SERVICES:
{services}
BOOKING: Via {', '.join(s['booking']['channels'])}. {s['booking']['cancellation_policy']}.
ESCALATE WHEN:
{triggers}""".strip()
