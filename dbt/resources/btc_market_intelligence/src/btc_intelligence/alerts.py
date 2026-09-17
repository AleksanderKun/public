from datetime import datetime, timezone
from typing import Any


def detect_alerts(features: dict[str, Any], timeframe: str = "4H") -> list[dict[str, Any]]:
    alerts = []
    timestamp = datetime.now(timezone.utc).isoformat()
    if features.get("oi_change_pct", 0) > 5 and abs(features.get("spot_cvd_change", 0)) < 1:
        alerts.append({"severity": "HIGH", "type": "LEVERAGE_WITHOUT_SPOT_CONFIRMATION", "evidence": ["open interest increased rapidly", "spot CVD remained flat"], "timeframe": timeframe, "timestamp": timestamp})
    if features.get("funding_percentile", 0) >= 95:
        alerts.append({"severity": "MEDIUM", "type": "EXTREME_POSITIVE_FUNDING", "evidence": ["funding entered the 95th percentile or higher"], "timeframe": timeframe, "timestamp": timestamp})
    if features.get("long_liquidation_notional", 0) > 0:
        alerts.append({"severity": "HIGH", "type": "LONG_LIQUIDATION_ACTIVITY", "evidence": ["public long liquidation activity observed"], "timeframe": timeframe, "timestamp": timestamp})
    return alerts