import csv
from datetime import datetime, timezone
from pathlib import Path

from .models import Observation, utc_now


def read_etf_flows(path: str | Path) -> list[Observation]:
    observations = []
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            timestamp = datetime.strptime(row["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            fund = row["fund"]
            observations.append(Observation(utc_now(), "etf_csv_import", fund, "etf", fund, "net_flow_usd", float(row["net_flow_usd"]), {"date": row["date"], "fund": fund}, timestamp))
    return observations