"""有界、單次使用的感測器時間配對；不控制曝光同步。"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import math
from threading import Condition
import time
from typing import Any

import numpy as np


@dataclass(frozen=True)
class EyeFrame:
    image_bgr: np.ndarray
    camera_id: str
    frame_id: int  # 本次 open 後各眼的程式序號，不是驅動序號。
    sensor_timestamp_ns: int | None
    exposure_time_us: int | None
    host_received_monotonic_ns: int
    timestamp_domain: str | None
    image_size: tuple[int, int]
    pixel_format: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class FramePair:
    left: EyeFrame | None
    right: EyeFrame | None
    left_timestamp_ns: int | None
    right_timestamp_ns: int | None
    delta_ms: float | None
    pair_id: int
    valid: bool
    discard_reason: str | None
    synchronization_mode: str = "timestamp_pairing_only"


class TimestampPairer:
    """選左右目前有界視窗中的最近時間對，非離線全域最佳配對。

    不等待未知未來影格；同距離優先較早影格，選中前的舊幀丟棄。
    所有移除的影格不重用。丟棄計數完整保留，事件紀錄本身有上限。
    """

    def __init__(
        self,
        max_pair_delta_ms: float = 10.0,
        queue_size: int = 6,
        max_age_ms: float = 500.0,
    ) -> None:
        if (
            not math.isfinite(max_pair_delta_ms)
            or max_pair_delta_ms < 0
            or not math.isfinite(max_age_ms)
            or max_age_ms <= 0
            or queue_size < 2
        ):
            raise ValueError("時間門檻須有限，age 須正數，queue 至少為 2。")
        self.max_delta_ns = int(max_pair_delta_ms * 1_000_000)
        self.max_age_ns = int(max_age_ms * 1_000_000)
        self.queue_size = queue_size
        self._queues: dict[str, deque[EyeFrame]] = {
            "left": deque(), "right": deque()
        }
        self._last: dict[str, int | None] = {"left": None, "right": None}
        self._domains: dict[str, str | None] = {
            "left": None, "right": None
        }
        self._reports: deque[FramePair] = deque(maxlen=2 * queue_size)
        self.discard_counts: Counter[str] = Counter()
        self._condition = Condition()
        self._error: str | None = None
        self._closed = False
        self._pair_id = 0

    def _result(
        self,
        left: EyeFrame | None,
        right: EyeFrame | None,
        reason: str | None,
    ) -> FramePair:
        self._pair_id += 1
        lt = None if left is None else left.sensor_timestamp_ns
        rt = None if right is None else right.sensor_timestamp_ns
        delta = None if lt is None or rt is None else abs(lt - rt) / 1e6
        return FramePair(
            left, right, lt, rt, delta, self._pair_id, reason is None, reason
        )

    def _discard(self, side: str, frame: EyeFrame, reason: str) -> None:
        self.discard_counts[reason] += 1
        self._reports.append(self._result(
            frame if side == "left" else None,
            frame if side == "right" else None,
            reason,
        ))

    def push(self, side: str, frame: EyeFrame) -> None:
        if side not in self._queues:
            raise ValueError("side 必須為 left 或 right。")
        with self._condition:
            if self._closed:
                return
            stamp = frame.sensor_timestamp_ns
            previous = self._last[side]
            domain = frame.timestamp_domain
            if (
                not isinstance(stamp, int) or isinstance(stamp, bool)
                or stamp < 0 or not isinstance(domain, str) or not domain
            ):
                self._discard(
                    side, frame, "missing_sensor_timestamp_or_domain"
                )
            elif self._domains[side] not in (None, domain):
                self._discard(side, frame, "timestamp_domain_changed")
            elif previous is not None and stamp <= previous:
                self._discard(side, frame, "non_increasing_sensor_timestamp")
            else:
                self._last[side] = stamp
                self._domains[side] = domain
                queue = self._queues[side]
                if len(queue) >= self.queue_size:
                    self._discard(side, queue.popleft(), "queue_overflow")
                queue.append(frame)
            self._condition.notify_all()

    def fail(self, message: str) -> None:
        with self._condition:
            self._error = message
            self._condition.notify_all()

    def close(self) -> None:
        with self._condition:
            self._closed = True
            for queue in self._queues.values():
                queue.clear()
            self._reports.clear()
            self._condition.notify_all()

    def read_pair(self, timeout_s: float = 3.0) -> FramePair:
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout 須為正有限數。")
        deadline = time.monotonic() + timeout_s
        with self._condition:
            while True:
                if self._error:
                    raise RuntimeError(self._error)
                if self._closed:
                    raise RuntimeError("配對器已關閉。")
                now = time.monotonic_ns()
                for side, queue in self._queues.items():
                    while queue and (
                        now - queue[0].host_received_monotonic_ns
                        > self.max_age_ns
                    ):
                        self._discard(side, queue.popleft(), "stale_frame")
                if self._reports:
                    return self._reports.popleft()
                left, right = self._queues["left"], self._queues["right"]
                if left and right:
                    if left[0].timestamp_domain != right[0].timestamp_domain:
                        self._discard(
                            "left", left.popleft(), "domain_mismatch"
                        )
                        self._discard(
                            "right", right.popleft(), "domain_mismatch"
                        )
                        continue
                    # push 已拒絕缺失時間戳；這裡明確縮窄型別。
                    lt = left[0].sensor_timestamp_ns
                    rt = right[0].sensor_timestamp_ns
                    assert lt is not None and rt is not None
                    candidates = []
                    for li, left_frame in enumerate(left):
                        for ri, right_frame in enumerate(right):
                            ls = left_frame.sensor_timestamp_ns
                            rs = right_frame.sensor_timestamp_ns
                            assert ls is not None and rs is not None
                            candidates.append((abs(ls - rs), li, ri))
                    delta, li, ri = min(candidates)
                    if delta > self.max_delta_ns:
                        side = "left" if lt <= rt else "right"
                        own = self._queues[side]
                        self._discard(side, own.popleft(), "delta_exceeded")
                        continue
                    for side, count in (("left", li), ("right", ri)):
                        for _ in range(count):
                            self._discard(
                                side, self._queues[side].popleft(),
                                "skipped_for_nearest",
                            )
                    return self._result(
                        left.popleft(), right.popleft(), None
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("等待雙眼影格逾時；沒有可輸出的影格對。")
                self._condition.wait(min(remaining, 0.1))
