"""單手食指尖預覽；不計算深度、不發送觸控或設備指令。"""

import argparse
import math
from pathlib import Path
import sys
import time


WINDOW_NAME = "MagicBlank - Webcam Test"


def fingertip_pixels(result, width, height):
    """沒有可用的畫面內指尖時回傳 None，不沿用上一幀的位置。"""
    if not result.hand_landmarks or len(result.hand_landmarks[0]) <= 8:
        return None
    tip = result.hand_landmarks[0][8]
    if not all(
        math.isfinite(value) and 0 <= value <= 1
        for value in (tip.x, tip.y)
    ):
        return None
    return (
        min(int(tip.x * width), width - 1),
        min(int(tip.y * height), height - 1),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--camera-index", type=int, default=0, help="攝影機編號，預設 0"
    )
    parser.add_argument(
        "--model", type=Path,
        default=Path(__file__).resolve().with_name("hand_landmarker.task"),
        help="模型檔路徑，預設與本程式同目錄",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="只檢查套件、模型及空白影像推論，不開攝影機",
    )
    args = parser.parse_args(argv)
    if not args.model.is_file():
        parser.error(f"找不到模型：{args.model}；請放在程式旁或使用 --model 指定。")

    try:
        import cv2
        import mediapipe as mp
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(f"套件無法載入：{exc}。請確認使用專案的虛擬環境。") from exc

    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(
            model_asset_path=str(args.model.resolve())
        ),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=1,
    )
    # 先載入模型；模型失敗時不開攝影機。
    landmarker = mp.tasks.vision.HandLandmarker.create_from_options(options)
    with landmarker:
        if args.check:
            blank = mp.Image(image_format=mp.ImageFormat.SRGB,
                             data=np.zeros((480, 640, 3), dtype=np.uint8))
            for timestamp in (0, 1):
                result = landmarker.detect_for_video(blank, timestamp)
                if fingertip_pixels(result, 640, 480) is not None:
                    raise RuntimeError("空白影像出現非預期的指尖結果。")
            print(
                f"Python {sys.version.split()[0]} / "
                f"OpenCV {cv2.__version__} / MediaPipe {mp.__version__}"
            )
            print("檢查通過：模型載入、兩幀空白影像推論及 LOST；未開啟攝影機。")
            return 0

        camera = cv2.VideoCapture(args.camera_index)
        try:
            if not camera.isOpened():
                raise RuntimeError(
                    "無法開啟攝影機。請檢查 Windows 相機權限、是否被其他程式占用，"
                    "或改用 --camera-index 1。"
                )
            cv2.namedWindow(WINDOW_NAME)
            print("這是 2D 指尖預覽，沒有深度或觸控判斷。點一下攝影機視窗，按 q 或 Esc 離開。")
            last_timestamp_ms = -1
            while True:
                ok, frame = camera.read()
                if not ok or frame is None or frame.size == 0:
                    raise RuntimeError("攝影機已開啟，但無法讀取影像。請確認連線或其他程式是否占用。")
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(
                    image_format=mp.ImageFormat.SRGB, data=rgb_frame
                )
                timestamp_ms = max(
                    time.monotonic_ns() // 1_000_000, last_timestamp_ms + 1
                )
                last_timestamp_ms = timestamp_ms
                result = landmarker.detect_for_video(image, timestamp_ms)

                height, width = frame.shape[:2]
                point = fingertip_pixels(result, width, height)
                status = "LOST"
                if point is not None:
                    cv2.circle(frame, point, 8, (0, 255, 0), -1)
                    status = f"TRACKING  x={point[0]}  y={point[1]} px"
                cv2.putText(frame, status, (15, 30), cv2.FONT_HERSHEY_SIMPLEX,
                            0.65, (0, 255, 255), 2)
                cv2.putText(frame, "2D ONLY - NO DEPTH / NO TOUCH", (15, 55),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
                cv2.imshow(WINDOW_NAME, frame)
                if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                    break
                visible = cv2.getWindowProperty(
                    WINDOW_NAME, cv2.WND_PROP_VISIBLE
                )
                if visible < 1:
                    break
        finally:
            camera.release()
            cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已停止測試。")
        raise SystemExit(130)
    except Exception as exc:
        print(f"啟動或執行失敗：{exc}", file=sys.stderr)
        raise SystemExit(1)
