from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


@dataclass(frozen=True)
class RegimeResult:
    primary_regime: str
    confidence: float
    evidence: list[str]
    counter_evidence: list[str]
    timestamp: datetime


def classify_price_oi_funding(
    price_change_pct: float, oi_change_pct: float, funding_rate: float
) -> RegimeResult:
    evidence: list[str] = []
    counter: list[str] = []
    if price_change_pct > 0 and oi_change_pct < 0:
        regime = "SHORT_SQUEEZE"
        evidence.extend(["price increased", "open interest decreased"])
    elif price_change_pct > 0 and oi_change_pct > 0 and funding_rate > 0:
        regime = "LONG_BUILDUP"
        evidence.extend(
            ["price increased", "open interest increased", "funding is positive"]
        )
    elif price_change_pct < 0 and oi_change_pct < 0:
        regime = "LONG_SQUEEZE"
        evidence.extend(["price decreased", "open interest decreased"])
    elif price_change_pct < 0 and oi_change_pct > 0 and funding_rate < 0:
        regime = "SHORT_BUILDUP"
        evidence.extend(
            ["price decreased", "open interest increased", "funding is negative"]
        )
    else:
        regime = "NEUTRAL"
        counter.append("price/OI/funding combination is not decisive")
    confidence = min(0.95, 0.5 + 0.1 * len(evidence)) if evidence else 0.4
    return RegimeResult(
        regime, confidence, evidence, counter, datetime.now(timezone.utc)
    )


def compute_cvd(trades: Iterable[dict[str, Any]]) -> dict[str, float | int]:
    buy_volume = 0.0
    sell_volume = 0.0
    count = 0
    for trade in trades:
        volume = float(trade["volume"])
        side = str(trade.get("side", "")).lower()
        is_buyer_maker = bool(trade.get("is_buyer_maker", False))
        is_buy = side == "buy" or (not side and not is_buyer_maker)
        if is_buy:
            buy_volume += volume
        else:
            sell_volume += volume
        count += 1
    return {
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "delta": buy_volume - sell_volume,
        "cvd": buy_volume - sell_volume,
        "trade_count": count,
    }


def market_structure(closes: list[float], lookback: int = 3) -> dict[str, Any]:
    if len(closes) < max(lookback * 2 + 1, 5):
        return {
            "status": "insufficient_data",
            "required_points": max(lookback * 2 + 1, 5),
        }
    recent = closes[-lookback:]
    previous = closes[-2 * lookback : -lookback]
    direction = (
        "UP"
        if recent[-1] > previous[-1]
        else "DOWN"
        if recent[-1] < previous[-1]
        else "RANGE"
    )
    return {
        "status": "ok",
        "direction": direction,
        "swing_high": max(closes),
        "swing_low": min(closes),
        "range_high": max(recent),
        "range_low": min(recent),
        "breakout": recent[-1] > max(previous),
        "failed_breakout": recent[-1] < max(previous) and max(recent) > max(previous),
    }


def liquidity_zones(
    current_price: float, levels: Iterable[dict[str, Any]], max_zones: int = 3
) -> dict[str, Any]:
    upper = sorted(
        (level for level in levels if float(level["price"]) > current_price),
        key=lambda item: float(item["price"]),
    )[:max_zones]
    lower = sorted(
        (level for level in levels if float(level["price"]) < current_price),
        key=lambda item: float(item["price"]),
        reverse=True,
    )[:max_zones]
    nearest = (
        "UP"
        if upper
        and (
            not lower
            or float(upper[0]["price"]) - current_price
            <= current_price - float(lower[0]["price"])
        )
        else "DOWN"
        if lower
        else "UNKNOWN"
    )
    return {
        "current_price": current_price,
        "upper": upper,
        "lower": lower,
        "nearest": nearest,
        "confidence": min(100, (len(upper) + len(lower)) * 15),
    }


def explainable_score(components: dict[str, float]) -> dict[str, Any]:
    bounded = {
        name: max(-25.0, min(25.0, float(value))) for name, value in components.items()
    }
    total = max(-100.0, min(100.0, sum(bounded.values())))
    bias = "BULLISH" if total > 20 else "BEARISH" if total < -20 else "NEUTRAL"
    return {
        "components": bounded,
        "total": total,
        "bias": bias,
        "is_model_estimate": True,
    }


def scenario_estimates(regime: str, score: float) -> list[dict[str, Any]]:
    weights = {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}
    if regime == "SHORT_SQUEEZE":
        weights["A"] += 0.15
        weights["C"] += 0.05
    elif regime == "LONG_BUILDUP":
        weights["B"] += 0.20
        weights["C"] += 0.10
    elif regime == "LONG_SQUEEZE":
        weights["C"] += 0.15
    elif score > 20:
        weights["D"] += 0.20
    total = sum(weights.values())
    estimates = [
        {
            "scenario": key,
            "probability": round(value / total, 4),
            "is_model_estimate": True,
            "confidence": 0.4,
        }
        for key, value in weights.items()
    ]
    estimates[-1]["probability"] = round(
        1.0 - sum(item["probability"] for item in estimates[:-1]), 4
    )
    return estimates


def ohlcv_indicators(
    candles: list[dict[str, float]], period: int = 14
) -> dict[str, Any]:
    if len(candles) < period + 1:
        return {"status": "insufficient_data", "required_points": period + 1}
    closes = [float(candle["close"]) for candle in candles]
    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    gains = [max(change, 0.0) for change in changes[-period:]]
    losses = [max(-change, 0.0) for change in changes[-period:]]
    average_gain = sum(gains) / period
    average_loss = sum(losses) / period
    rsi = (
        100.0
        if average_loss == 0
        else 100.0 - (100.0 / (1.0 + average_gain / average_loss))
    )
    true_ranges = [
        max(
            float(c["high"]) - float(c["low"]),
            abs(float(c["high"]) - closes[i - 1]),
            abs(float(c["low"]) - closes[i - 1]),
        )
        for i, c in enumerate(candles[1:], 1)
    ]
    atr = sum(true_ranges[-period:]) / period
    returns = [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes))]
    mean_return = sum(returns[-period:]) / period
    volatility = (
        sum((value - mean_return) ** 2 for value in returns[-period:]) / period
    ) ** 0.5
    fast = sum(closes[-12:]) / min(12, len(closes))
    slow = sum(closes[-26:]) / min(26, len(closes))
    return {
        "status": "ok",
        "rsi": rsi,
        "atr": atr,
        "rolling_volatility": volatility,
        "macd_proxy": fast - slow,
        "last_close": closes[-1],
    }


def classify_market_regime(
    features: dict[str, float], timestamp: datetime | None = None
) -> dict[str, Any]:
    price = features.get("price_change_pct", 0.0)
    oi = features.get("oi_change_pct", 0.0)
    funding = features.get("funding_rate", 0.0)
    spot_cvd = features.get("spot_cvd_change", 0.0)
    liquidations = features.get("liquidation_notional", 0.0)
    result = classify_price_oi_funding(price, oi, funding)
    evidence = list(result.evidence)
    counter = list(result.counter_evidence)
    regime = result.primary_regime
    if price > 0 and spot_cvd > 0 and oi <= 1.0:
        regime = "SPOT_LED_RALLY"
        evidence.append("spot CVD increased while open interest remained controlled")
    elif price > 0 and spot_cvd <= 0 and oi > 1.0 and funding > 0:
        regime = "LEVERAGE_LED_RALLY"
        evidence.extend(["spot CVD was weak", "open interest and funding increased"])
    if liquidations > 0:
        evidence.append("public liquidation activity was observed")
    confidence = min(0.95, 0.45 + min(0.1 * len(evidence), 0.45))
    return {
        "primary_regime": regime,
        "confidence": confidence,
        "evidence": evidence,
        "counter_evidence": counter,
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        "is_model_estimate": True,
    }


def liquidity_report(
    current_price: float, levels: list[dict[str, Any]]
) -> dict[str, Any]:
    report = liquidity_zones(current_price, levels)
    upper_score = sum(float(item.get("weight", 1.0)) for item in report["upper"])
    lower_score = sum(float(item.get("weight", 1.0)) for item in report["lower"])
    report["asymmetry"] = (
        "BULLISH"
        if lower_score > upper_score
        else "BEARISH"
        if upper_score > lower_score
        else "NEUTRAL"
    )
    return report


def market_report(
    facts: list[str], model_output: dict[str, Any], hypotheses: list[str]
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "FACT": facts,
        "MODEL_OUTPUT": model_output,
        "HYPOTHESIS": hypotheses,
        "disclaimer": "Model estimates are not facts or trading instructions.",
    }
