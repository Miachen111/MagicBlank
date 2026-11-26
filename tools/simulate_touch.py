"""Print one simulated cycle as JSON Lines; no MQTT or GPIO connection."""

import json
import sys
import time
import uuid

from check_contract import validate_event


def main():
    session = str(uuid.uuid4())
    steps = (
        ("hover", 30.0), ("touch_down", 2.0),
        ("touch_up", 20.0), ("tracking_lost", None),
    )
    for seq, (name, distance) in enumerate(steps, start=1):
        lost = name == "tracking_lost"
        event = {
            "schema_version": 1, "device_id": "desk-01", "session_id": session,
            "seq": seq, "timestamp_ms": time.time_ns() // 1_000_000,
            "source": "simulated", "mode": "surface_touch", "event": name,
            "x": None if lost else 0.20, "y": None if lost else 0.50,
            "distance_mm": distance, "confidence": None,
        }
        validate_event(event)
        print(json.dumps(event, allow_nan=False), flush=True)
    print(
        "Simulated data only; no hardware actions executed.", file=sys.stderr
    )


if __name__ == "__main__":
    main()
