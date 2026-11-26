"""MediaPipe Tasks 單手影像 XY；不輸出桌面座標、深度或觸碰分數。"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import time
from typing import Any

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


@dataclass(frozen=True)
class HandTrackingResult:
    hand_detected: bool
    image_xy_normalized: tuple[float, float] | None
    image_xy_pixels: tuple[int, int] | None
    tracker_timestamp_ms: int


class HandTracker:
    """單一 VIDEO session；每次 detect 都使用新結果，無手時不保留舊座標。"""

    def __init__(self, model_path: str | Path) -> None:
        model = Path(model_path)
        if not model.is_file():
            raise FileNotFoundError(
                f"找不到 Hand Landmarker 模型：{model}；請自行準備 .task 檔。"
            )
        options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
        )
        self._landmarker: Any = (
            vision.HandLandmarker.create_from_options(options)
        )
        self._start_ns = time.monotonic_ns()
        self._last_timestamp_ms = -1

    def track(self, image_bgr: np.ndarray) -> HandTrackingResult:
        if self._landmarker is None:
            raise RuntimeError("HandTracker 已關閉。")
        if (
            image_bgr.dtype != np.uint8
            or image_bgr.ndim != 3
            or image_bgr.shape[2] != 3
        ):
            raise ValueError("追蹤輸入須為 uint8 三通道 BGR 影像。")
        height, width = image_bgr.shape[:2]
        if width == 0 or height == 0:
            raise ValueError("追蹤輸入不可為空影像。")
        # VIDEO 的時間戳是本 session 的處理排程時間，並非 Frame 的取得時間、
        # 感測器時間或影片 PTS。max 保證快於 1ms 的呼叫也嚴格遞增。
        elapsed_ms = (time.monotonic_ns() - self._start_ns) // 1_000_000
        timestamp_ms = max(elapsed_ms, self._last_timestamp_ms + 1)
        self._last_timestamp_ms = timestamp_ms
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        result = self._landmarker.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp_ms
        )
        invalid = HandTrackingResult(False, None, None, timestamp_ms)
        if not result.hand_landmarks:
            return invalid
        tip = result.hand_landmarks[0][8]
        x, y = float(tip.x), float(tip.y)
        # 拒絕畫面外或非有限數，不把無效座標夾到邊緣當成有效指尖。
        if (
            not math.isfinite(x)
            or not math.isfinite(y)
            or not (0 <= x < 1 and 0 <= y < 1)
        ):
            return invalid
        return HandTrackingResult(
            True,
            (x, y),
            (int(x * width), int(y * height)),
            timestamp_ms,
        )

    def close(self) -> None:
        landmarker, self._landmarker = self._landmarker, None
        if landmarker is not None:
            landmarker.close()

    def __enter__(self) -> HandTracker:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()
