"""單路／影片及雙路 BGR 來源；雙路僅時間配對，不保證曝光同步。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from threading import Event, Thread
import time
from typing import Any

import cv2
import numpy as np

from .stereo_pairing import EyeFrame, FramePair, TimestampPairer


class SourceOpenError(RuntimeError):
    """來源無法開啟或設定。"""


class SourceReadError(RuntimeError):
    """已開啟的來源無法取得有效影格；不同於影片正常結束。"""


@dataclass(frozen=True)
class Frame:
    image_bgr: np.ndarray
    frame_id: int
    source: str
    timestamp_ns: int
    timestamp_domain: str = "host_monotonic"
    timestamp_origin: str = "主機完成取得影格後的 monotonic_ns；非曝光時間"
    metadata: dict[str, Any] = field(default_factory=dict)


class FrameSource(ABC):
    """read() 回傳 Frame；只有影片確認結束時回傳 None，其餘失敗拋例外。"""

    @abstractmethod
    def open(self) -> None:
        pass

    @abstractmethod
    def read(self) -> Frame | None:
        pass

    @abstractmethod
    def close(self) -> None:
        pass

    def __enter__(self) -> FrameSource:
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


class Picamera2Source(FrameSource):
    """預備的 Pi 單路路徑，實際相機／驅動相容性尚未驗證。"""

    def __init__(
        self,
        camera_index: int = 0,
        width: int = 640,
        height: int = 480,
        fps: float = 30.0,
    ) -> None:
        if (
            camera_index < 0
            or width <= 0
            or height <= 0
            or not 0 < fps < float("inf")
        ):
            raise ValueError("camera index 須非負，尺寸與目標幀率須為正有限數。")
        self.camera_index = camera_index
        self.size = (width, height)
        self.fps = fps
        self._camera: Any = None
        self._frame_id = 0

    def open(self) -> None:
        if self._camera is not None:
            raise SourceOpenError("相機已開啟。")
        try:
            # 延後載入：沒有 Picamera2 的電腦仍能使用影片 adapter。
            from picamera2 import Picamera2
        except ImportError as exc:
            raise SourceOpenError(
                "缺少 Picamera2／libcamera 系統相依項目。請先確認 Pi OS 與相機支援；"
                "本機影片來源不需要 Picamera2。"
            ) from exc
        try:
            self._camera = Picamera2(camera_num=self.camera_index)
            # Picamera2 的 RGB888 命名依 libcamera 慣例；陣列位元組為 B,G,R。
            # 必須在實機以已知色卡確認通道順序，不以格式名稱推定已通過驗證。
            config = self._camera.create_video_configuration(
                main={"size": self.size, "format": "RGB888"},
                controls={"FrameRate": self.fps},
            )
            self._camera.configure(config)
            self._camera.start()
            self._frame_id = 0
        except Exception as exc:
            self.close()
            raise SourceOpenError(f"Pi 單路相機開啟失敗：{exc}") from exc

    def read(self) -> Frame:
        if self._camera is None:
            raise SourceReadError("相機尚未開啟。")
        try:
            request = self._camera.capture_request()
            try:
                image = request.make_array("main").copy()
                timestamp_ns = time.monotonic_ns()
                sdk_metadata = request.get_metadata()
            finally:
                request.release()
            if image.size == 0 or image.ndim != 3 or image.shape[2] != 3:
                raise ValueError("相機未提供三通道 BGR 影像。")
            metadata: dict[str, Any] = {}
            if "SensorTimestamp" in sdk_metadata:
                metadata["sensor_timestamp_raw"] = sdk_metadata[
                    "SensorTimestamp"
                ]
                metadata["sensor_timestamp_origin"] = (
                    "Picamera2 metadata.SensorTimestamp"
                )
                metadata["sensor_timestamp_domain"] = "SDK／驅動定義，尚未確認；不與主機時間相減"
            frame = Frame(
                image,
                self._frame_id,
                f"picamera2:{self.camera_index}",
                timestamp_ns,
                metadata=metadata,
            )
            self._frame_id += 1
            return frame
        except Exception as exc:
            raise SourceReadError(f"Pi 相機讀取失敗（不是影片結束）：{exc}") from exc

    def close(self) -> None:
        camera, self._camera = self._camera, None
        if camera is not None:
            # close 會釋放 Picamera2 資源，也適用於尚未成功 start 的情況。
            camera.close()


class VideoFileSource(FrameSource):
    """OpenCV 本機影片解碼；不以 VideoCapture(0) 代替 Pi CSI 驅動。"""

    def __init__(
        self,
        path: str | Path,
        width: int = 640,
        height: int = 480,
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("影像尺寸須為正數。")
        self.path = Path(path)
        self.size = (width, height)
        self._capture: Any = None
        self._frame_id = 0
        self._frame_count = 0
        self._ended = False

    def open(self) -> None:
        if self._capture is not None:
            raise SourceOpenError("影片已開啟。")
        if not self.path.is_file():
            raise SourceOpenError(f"找不到本機影片：{self.path}")
        try:
            self._capture = cv2.VideoCapture(str(self.path))
            if not self._capture.isOpened():
                raise ValueError("OpenCV 無法開啟影片，請確認格式與解碼器。")
            count = self._capture.get(cv2.CAP_PROP_FRAME_COUNT)
            self._frame_count = (
                int(count) if np.isfinite(count) and count > 0 else 0
            )
            self._frame_id = 0
            self._ended = False
        except Exception as exc:
            self.close()
            raise SourceOpenError(f"影片開啟失敗：{exc}") from exc

    def read(self) -> Frame | None:
        if self._capture is None:
            raise SourceReadError("影片尚未開啟。")
        if self._ended:
            return None
        try:
            ok, image = self._capture.read()
            if not ok:
                # OpenCV 的 False 同時可能表示 EOF 或解碼錯誤。保守判斷：
                # 必須已讀完容器回報的幀數，才能當作正常結束。
                if (
                    self._frame_count > 0
                    and self._frame_id >= self._frame_count
                ):
                    self._ended = True
                    return None
                raise ValueError("影片提早解碼失敗，或幀數未知而無法確認正常 EOF。")
            timestamp_ns = time.monotonic_ns()
            if image is None or image.size == 0:
                raise ValueError("解碼器回傳空影像。")
            image = cv2.resize(image, self.size)
            frame = Frame(
                image,
                self._frame_id,
                "video_file",
                timestamp_ns,
                metadata={
                    "video_position_ms_raw": self._capture.get(
                        cv2.CAP_PROP_POS_MSEC
                    ),
                    "video_position_origin": (
                        "OpenCV 解碼位置，影片媒體時間；"
                        "非擷取／曝光時間，可能不可用"
                    ),
                },
            )
            self._frame_id += 1
            return frame
        except Exception as exc:
            raise SourceReadError(f"影片讀取失敗：{exc}") from exc

    def close(self) -> None:
        capture, self._capture = self._capture, None
        if capture is not None:
            capture.release()


def json_value(value: Any) -> Any:
    """把 SDK 的設定轉為可保存的 JSON；未知 SDK 物件保留文字表示。"""
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def load_picamera2() -> Any:
    try:
        from picamera2 import Picamera2
    except ImportError as exc:
        raise SourceOpenError(
            "找不到 Picamera2／libcamera；請在相容的 Pi OS 環境執行，"
            "勿以 Windows 或 pip 單獨安裝取代系統綁定。"
        ) from exc
    return Picamera2


def geometry_record(config: dict[str, Any], metadata: dict) -> dict:
    """保存會影響幾何的實際設定；不把它當成內外參校正結果。"""
    return json_value({
        "main": config.get("main"),
        "raw": config.get("raw"),
        "sensor": config.get("sensor"),
        "transform": config.get("transform"),
        "scaler_crop": metadata.get("ScalerCrop"),
    })


class StereoCamera:
    """兩個獨立 worker，輸出有效配對或明確的丟棄事件。

    mapping 中的 index 和 Id 必須同時符合當次枚舉；不自動交換左右。
    同一 Pi 開機時間域可比較不等於同時曝光，無軟體同步控制項。
    """

    synchronization_mode = "timestamp_pairing_only"

    def __init__(
        self,
        mapping_path: str | Path,
        width: int = 640,
        height: int = 480,
        fps: float = 30.0,
        max_pair_delta_ms: float = 10.0,
        queue_size: int = 6,
        timeout_s: float = 3.0,
        max_age_ms: float = 500.0,
    ) -> None:
        if (
            width <= 0 or height <= 0
            or not math.isfinite(fps) or fps <= 0
            or not math.isfinite(timeout_s) or timeout_s <= 0
        ):
            raise ValueError("尺寸、fps、timeout 須為正有限值。")
        self.mapping_path = Path(mapping_path)
        self.size = (width, height)
        self.fps = fps
        self.timeout_s = timeout_s
        self._pair_options = (max_pair_delta_ms, queue_size, max_age_ms)
        self._pairer: TimestampPairer | None = None
        self._cameras: dict[str, Any] = {}
        self._threads: list[Thread] = []
        self._stop = Event()
        self.session_info: dict[str, Any] = {}
        self._domain: str | None = None

    def open(self) -> None:
        if self._cameras:
            raise SourceOpenError("雙路相機已開啟。")
        try:
            picamera2 = load_picamera2()
            mapping = json.loads(self.mapping_path.read_text(encoding="utf-8"))
            infos = picamera2.global_camera_info()
            selected = {}
            for side in ("left", "right"):
                entry = mapping[side]
                index, identity = entry["index"], entry["camera_id"]
                if (
                    not isinstance(index, int) or isinstance(index, bool)
                    or not 0 <= index < len(infos)
                    or not isinstance(identity, str) or not identity.strip()
                    or infos[index].get("Id") != identity
                    or str(infos[index].get("Model", "")).lower() != "imx219"
                ):
                    raise ValueError(f"{side} 索引／Id／IMX219 型號不符。")
                selected[side] = entry
            if (
                selected["left"]["index"] == selected["right"]["index"]
                or selected["left"]["camera_id"]
                == selected["right"]["camera_id"]
                or not mapping.get("mounting_description")
            ):
                raise ValueError("左右須不同，且須記錄實體安裝方向。")
            # 兩眼共用同一 Pi 的 libcamera 開機時間域，非 host monotonic。
            boot_id = (
                Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            )
            if not boot_id:
                raise ValueError("無法取得本次 Pi boot id，拒絕推定時間域。")
            self._domain = f"libcamera_sensor_boot:{boot_id}"
            self._stop.clear()
            self._pairer = TimestampPairer(*self._pair_options)
            self.session_info = {
                "mapping": mapping,
                "synchronization_mode": self.synchronization_mode,
                "timestamp_domain": self._domain,
                "requested_size": list(self.size),
                "requested_fps": self.fps,
                "max_pair_delta_ms": self._pair_options[0],
                "queue_size": self._pair_options[1],
                "max_age_ms": self._pair_options[2],
                "cameras": {},
            }
            for side, entry in selected.items():
                camera = picamera2(camera_num=entry["index"])
                self._cameras[side] = camera
                if not callable(getattr(camera, "cancel_all_and_flush", None)):
                    raise ValueError("此 Picamera2 缺少取消 API，需確認版本。")
                config = camera.create_video_configuration(
                    main={"size": self.size, "format": "RGB888"},
                    controls={"FrameRate": self.fps},
                    queue=False,
                )
                camera.configure(config)
                actual = json_value(camera.camera_configuration())
                if (
                    actual["main"]["size"] != list(self.size)
                    or actual["main"]["format"] != "RGB888"
                ):
                    raise ValueError("SDK 調整了尺寸／格式，請重新指定設定。")
                self.session_info["cameras"][side] = {
                    "camera_id": entry["camera_id"],
                    "index": entry["index"],
                    "configuration": actual,
                    "sensor_modes": json_value(camera.sensor_modes),
                    "camera_properties": json_value(camera.camera_properties),
                    "camera_controls": json_value(camera.camera_controls),
                }
            # 先後啟動只代表開始擷取，絕不宣稱同步。
            for camera in self._cameras.values():
                camera.start()
            for side in ("left", "right"):
                thread = Thread(
                    target=self._capture_worker, args=(side,), daemon=True
                )
                self._threads.append(thread)
                thread.start()
        except BaseException as exc:
            try:
                self.close()
            except Exception as cleanup:
                exc.add_note(f"清理雙路相機時另發生：{cleanup}")
            if not isinstance(exc, Exception):
                raise
            raise SourceOpenError(f"雙路開啟失敗：{exc}") from exc

    def _capture_worker(self, side: str) -> None:
        camera = self._cameras[side]
        pairer = self._pairer
        assert pairer is not None
        record = self.session_info["cameras"][side]
        frame_id = 0
        pending = None
        try:
            while not self._stop.is_set():
                pending = camera.capture_request(wait=False)
                deadline = time.monotonic() + self.timeout_s
                request = None
                while not self._stop.is_set():
                    try:
                        request = camera.wait(pending, timeout=0.1)
                        pending = None
                        break
                    except TimeoutError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError(f"{side} capture_request 逾時。")
                if request is None:
                    break
                try:
                    image = request.make_array("main").copy()
                    received = time.monotonic_ns()
                    metadata = request.get_metadata()
                finally:
                    request.release()
                if (
                    image.dtype != np.uint8 or image.ndim != 3
                    or image.shape[2] != 3
                    or (image.shape[1], image.shape[0]) != self.size
                ):
                    raise ValueError(f"{side} 影像格式／尺寸不符。")
                stamp = metadata.get("SensorTimestamp")
                exposure = metadata.get("ExposureTime")
                frame = EyeFrame(
                    image, record["camera_id"], frame_id,
                    int(stamp) if isinstance(stamp, (int, np.integer))
                    and stamp >= 0 else None,
                    int(exposure) if isinstance(exposure, (int, np.integer))
                    and exposure >= 0 else None,
                    received, self._domain, self.size, "RGB888",
                    {
                        "sdk": json_value(metadata),
                        "geometry": geometry_record(
                            record["configuration"], metadata
                        ),
                        "array_color_order": "BGR",
                        "frame_id_origin": "per_eye_application_sequence",
                    },
                )
                frame_id += 1
                pairer.push(side, frame)
        except Exception as exc:
            if not self._stop.is_set():
                pairer.fail(f"{side} 擷取失敗：{exc}")
                self._stop.set()
        finally:
            if pending is not None:
                # SDK 取消待辦 job；若剛好完成，仍取回並釋放其 request。
                try:
                    camera.cancel_all_and_flush()
                    completed = camera.wait(pending, timeout=0)
                except Exception:
                    pass
                else:
                    completed.release()

    def read_pair(self, timeout_s: float | None = None) -> FramePair:
        if self._pairer is None:
            raise SourceReadError("雙路相機尚未開啟。")
        try:
            return self._pairer.read_pair(
                self.timeout_s if timeout_s is None else timeout_s
            )
        except Exception as exc:
            raise SourceReadError(f"雙路配對失敗：{exc}") from exc

    def close(self) -> None:
        self._stop.set()
        if self._pairer is not None:
            self._pairer.close()
        errors = []
        for thread in self._threads:
            if thread.ident is not None:
                thread.join(timeout=self.timeout_s + 1)
                if thread.is_alive():
                    errors.append("擷取 worker 未退出；驅動可能阻塞。")
        for camera in self._cameras.values():
            try:
                camera.cancel_all_and_flush()
            except Exception as exc:
                errors.append(str(exc))
            finally:
                try:
                    camera.close()
                except Exception as exc:
                    errors.append(str(exc))
        self._threads.clear()
        self._cameras.clear()
        self._pairer = None
        if errors:
            raise RuntimeError("；".join(errors))

    def __enter__(self) -> StereoCamera:
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()
