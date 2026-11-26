"""Validate shared examples/config without hardware or third-party packages."""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVENTS = {"hover", "touch_down", "touch_up", "tracking_lost"}
FIELDS = {
    "schema_version", "device_id", "session_id", "seq", "timestamp_ms",
    "source", "mode", "event", "x", "y", "distance_mm", "confidence",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, low=0, high=None):
    return (
        type(value) in (int, float) and math.isfinite(value)
        and value >= low and (high is None or value <= high)
    )


def validate_event(event):
    require(
        isinstance(event, dict) and set(event) == FIELDS,
        "Unexpected event fields",
    )
    require(
        type(event["schema_version"]) is int and event["schema_version"] == 1,
        "Invalid version",
    )
    for key in ("device_id", "session_id"):
        require(
            isinstance(event[key], str) and bool(event[key].strip()),
            f"Invalid {key}",
        )
    for key, minimum in (("seq", 1), ("timestamp_ms", 0)):
        require(
            type(event[key]) is int and event[key] >= minimum, f"Invalid {key}"
        )
    require(event["source"] in ("vision", "simulated"), "Invalid source")
    require(event["mode"] in ("surface_touch", "pinch"), "Invalid mode")
    require(event["event"] in EVENTS, "Invalid event")
    if event["event"] == "tracking_lost":
        require(
            all(
                event[key] is None
                for key in ("x", "y", "distance_mm", "confidence")
            ),
            "Lost tracking must clear measurements",
        )
    else:
        require(
            number(event["x"], high=1) and number(event["y"], high=1),
            "Invalid coordinates",
        )
    require(
        event["distance_mm"] is None or number(event["distance_mm"]),
        "Invalid distance",
    )
    require(
        event["confidence"] is None or number(event["confidence"], high=1),
        "Invalid confidence",
    )
    if event["mode"] == "surface_touch" and event["event"] == "touch_down":
        require(
            number(event["distance_mm"]), "Surface touch requires valid depth"
        )


def validate_buttons(config):
    require(
        type(config.get("schema_version")) is int
        and config["schema_version"] == 1,
        "Invalid button version",
    )
    buttons = config.get("buttons")
    require(
        isinstance(buttons, list) and len(buttons) == 3,
        "MVP requires three buttons",
    )
    ids = set()
    for button in buttons:
        require(isinstance(button, dict), "Invalid button")
        for key in ("id", "label", "action"):
            require(
                isinstance(button.get(key), str) and bool(button[key].strip()),
                f"Invalid button {key}",
            )
        require(button["id"] not in ids, "Duplicate button id")
        ids.add(button["id"])
        require(type(button.get("enabled")) is bool, "Invalid enabled flag")
        for axis in ("x", "y"):
            lo, hi = button.get(f"{axis}_min"), button.get(f"{axis}_max")
            require(
                number(lo, high=1) and number(hi, high=1) and lo < hi,
                "Invalid bounds",
            )
    for index, left in enumerate(buttons):
        for right in buttons[index + 1:]:
            overlap = all(
                max(left[f"{axis}_min"], right[f"{axis}_min"])
                < min(left[f"{axis}_max"], right[f"{axis}_max"])
                for axis in ("x", "y")
            )
            require(not overlap, "Buttons overlap")


def main():
    examples = json.loads(
        (ROOT / "shared/events.example.json").read_text(encoding="utf-8")
    )
    require(isinstance(examples, list) and bool(examples), "Missing examples")
    last_sequence = {}
    for event in examples:
        validate_event(event)
        key = (event["device_id"], event["session_id"])
        require(
            event["seq"] > last_sequence.get(key, 0), "Sequence must increase"
        )
        last_sequence[key] = event["seq"]
    validate_buttons(json.loads(
        (ROOT / "shared/buttons.json").read_text(encoding="utf-8")
    ))
    print(f"PASS: {len(examples)} example events and three button regions")


if __name__ == "__main__":
    main()
