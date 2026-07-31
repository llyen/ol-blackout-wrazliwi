from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

STREAM_FILES = {
    "weather_readings": "weather_readings.jsonl",
    "outage_events": "outage_events.jsonl",
    "emergency_calls": "emergency_calls.jsonl",
    "telecom_coverage": "telecom_coverage.jsonl",
}
BASE = Path(__file__).resolve().parent
DATA = BASE / "datasets"


def parse_time(value: str | None):
    return datetime.fromisoformat(value) if value else None


def iter_events(streams, start=None, end=None):
    for stream in streams:
        with (DATA / STREAM_FILES[stream]).open(encoding="utf-8") as f:
            for line in f:
                event = json.loads(line)
                event["_stream"] = stream
                ts = parse_time(event["event_time"])
                if start and ts < start:
                    continue
                if end and ts > end:
                    continue
                yield event


def main() -> None:
    parser = argparse.ArgumentParser(description="Send blackout/winter streams to Fabric Eventstream/Event Hub.")
    parser.add_argument("--stream", action="append", choices=STREAM_FILES.keys(), help="Repeatable stream name. Default: all.")
    parser.add_argument("--speed", type=float, default=120.0, help="Simulation speed multiplier.")
    parser.add_argument("--from", dest="from_time", help="ISO start time filter.")
    parser.add_argument("--to", dest="to_time", help="ISO end time filter.")
    parser.add_argument("--dry-run", action="store_true", help="Offline mode without dependencies or credentials.")
    args = parser.parse_args()

    streams = args.stream or list(STREAM_FILES)
    events = sorted(iter_events(streams, parse_time(args.from_time), parse_time(args.to_time)), key=lambda e: e["event_time"])
    if args.dry_run:
        out = DATA / "derived" / ("dry_run_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".jsonl")
        out.parent.mkdir(exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            for event in events[:2000]:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        print(f"DRY RUN OK: {len(events)} events selected from {streams}; sample written to {out}")
        for event in events[:5]:
            print(json.dumps(event, ensure_ascii=False))
        return

    from azure.eventhub import EventData, EventHubProducerClient  # lazy import

    producer = EventHubProducerClient.from_connection_string(
        conn_str=os.environ["EVENTHUB_CONNECTION_STR"],
        eventhub_name=os.environ.get("EVENTHUB_NAME"),
    )
    prev = None
    with producer:
        batch = producer.create_batch()
        for event in events:
            ts = parse_time(event["event_time"])
            if prev:
                time.sleep(max(0, (ts - prev).total_seconds() / args.speed))
            prev = ts
            payload = json.dumps(event, ensure_ascii=False)
            try:
                batch.add(EventData(payload))
            except ValueError:
                producer.send_batch(batch)
                batch = producer.create_batch()
                batch.add(EventData(payload))
        if len(batch) > 0:
            producer.send_batch(batch)
    print(f"SENT OK: {len(events)} events")


if __name__ == "__main__":
    main()
