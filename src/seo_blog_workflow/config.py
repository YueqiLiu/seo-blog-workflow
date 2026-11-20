"""Configuration and deterministic selection rules; no network side effects."""
import json
from pathlib import Path
from zoneinfo import ZoneInfo


def load_config(path):
    config = json.loads(Path(path).read_text())
    if not config["product"]["website"].startswith("https://"):
        raise ValueError("product.website must use HTTPS")
    selection = config["selection"]
    for prefix in ("volume", "kd"):
        low, high = selection[f"{prefix}_min"], selection[f"{prefix}_max"]
        if low < 0 or (high is not None and high < low):
            raise ValueError(f"Invalid {prefix} range")
    if selection["kd_min"] > 100 or (selection["kd_max"] is not None and selection["kd_max"] > 100):
        raise ValueError("KD must be between 0 and 100")
    if not 0 <= selection["relevance_min"] <= 100:
        raise ValueError("Relevance must be between 0 and 100")
    if selection["missing_metrics"] not in {"exclude", "allow"}:
        raise ValueError("missing_metrics must be exclude or allow")
    publication = config["publication"]
    if type(publication["daily_target"]) is not int or publication["daily_target"] < 0:
        raise ValueError("daily_target must be a nonnegative integer")
    ZoneInfo(publication["timezone"])
    if publication["mode"] not in {"draft", "publish"}:
        raise ValueError("publication.mode must be draft or publish")
    if set(config["sources"]) - {"product_hunt", "x", "google_trends", "semrush"}:
        raise ValueError("Unknown source")
    if any(type(enabled) is not bool for enabled in config["sources"].values()):
        raise ValueError("Source switches must be booleans")
    return config


def select_keyword(candidate, config):
    """Return acceptance and reason. Missing model assessments never pass."""
    rules = config["selection"]
    score = candidate.get("relevance_score")
    if not isinstance(score, (int, float)) or not rules["relevance_min"] <= score <= 100:
        return False, "product_relevance"
    return select_metrics(candidate, config)


def select_metrics(candidate, config):
    """Shared metric filtering for discovery and generation."""
    rules = config['selection']
    missing = False
    for field, prefix in (("search_volume", "volume"), ("kd", "kd")):
        value = candidate.get(field)
        if value is None:
            missing = True
            if rules["missing_metrics"] == "exclude":
                return False, "missing_metrics"
            continue
        upper = rules[f"{prefix}_max"]
        if value < rules[f"{prefix}_min"] or (upper is not None and value > upper):
            return False, f"{prefix}_outside_range"
    return True, "selected_unverified_metrics" if missing else "selected"


def remaining_publications(config, published_at, now):
    """Count actual publication instants in the configured local day."""
    zone = ZoneInfo(config["publication"]["timezone"])
    if now.tzinfo is None or any(value.tzinfo is None for value in published_at):
        raise ValueError("Publication timestamps must be timezone-aware")
    today = now.astimezone(zone).date()
    count = sum(value.astimezone(zone).date() == today for value in published_at)
    return max(0, config["publication"]["daily_target"] - count)
