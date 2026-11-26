"""MagicBlank single-camera pinch test. Place next to hand_landmarker.task."""
from math import dist
from pathlib import Path
from time import monotonic_ns

CLOSE_RATIO = 0.25
OPEN_RATIO = 0.40
DWELL_MS = 100


class PinchDetector:
    """Require an open hand after tracking starts or is lost."""

    def __init__(self):
        self.state = "WAIT_OPEN"
        self.since = None
        self.tracked = False

    def update(self, ratio, now):
        if ratio is None:
            event = "tracking_lost" if self.tracked else None
            self.tracked = False
            self.state = "WAIT_OPEN"
            self.since = None
            return event

        self.tracked = True
        if self.state == "READY":
            crossing = ratio < CLOSE_RATIO
            next_state, event = "PRESSED", "touch_down"
        else:
            crossing = ratio > OPEN_RATIO
            next_state = "READY"
            event = "touch_up" if self.state == "PRESSED" else None

        if not crossing:
            self.since = None
            return None
        if self.since is None:
            self.since = now
        if now - self.since < DWELL_MS:
            return None
        self.since = None
        self.state = next_state
        return event


def main():
    import cv2
    import mediapipe as mp

    model = Path(__file__).with_name("hand_landmarker.task")
    if not model.is_file():
        raise SystemExit("Place hand_landmarker.task beside test_pinch.py.")
    vision = mp.tasks.vision
    options = vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=1,
    )
    detector = PinchDetector()
    camera = cv2.VideoCapture(0)
    last_ms = -1
    try:
        if not camera.isOpened():
            raise RuntimeError("Cannot open webcam 0. Close other camera apps.")
        with vision.HandLandmarker.create_from_options(options) as landmarker:
            while True:
                ok, frame = camera.read()
                if not ok:
                    raise RuntimeError("Cannot read the webcam.")
                now = max(last_ms + 1, monotonic_ns() // 1_000_000)
                last_ms = now
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = landmarker.detect_for_video(image, now)
                ratio = None
                if result.hand_landmarks:
                    hand = result.hand_landmarks[0]
                    height, width = frame.shape[:2]
                    points = [(p.x * width, p.y * height) for p in hand]
                    palm_width = dist(points[5], points[17])
                    if palm_width >= 1:
                        ratio = dist(points[4], points[8]) / palm_width
                    for i, color in [(4, (0, 165, 255)), (8, (0, 255, 0))]:
                        x, y = points[i]
                        cv2.circle(frame, (round(x), round(y)), 7, color, -1)
                event = detector.update(ratio, now)
                if event:
                    print(f"mode=pinch  {event}", flush=True)
                label = "LOST" if ratio is None else f"{detector.state}  ratio={ratio:.2f}"
                cv2.putText(frame, "PINCH  " + label, (12, 32),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
                cv2.imshow("MagicBlank - Pinch (q to quit)", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
