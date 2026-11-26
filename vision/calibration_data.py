"""校正資料的 PNG／JSON／NPZ 存取；不含任何擷取或假校正值。"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .stereo_pairing import EyeFrame, FramePair


MATRIX_SHAPES = {
    "K1": (3, 3), "K2": (3, 3), "R": (3, 3), "T": (3, 1),
    "R1": (3, 3), "R2": (3, 3), "P1": (3, 4), "P2": (3, 4),
    "Q": (4, 4),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json_new(path: Path, value: dict) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text + "\n")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def eye_metadata(frame: EyeFrame) -> dict:
    # 不用 asdict(frame)：它會深複製大型影像。
    return {
        "camera_id": frame.camera_id,
        "frame_id": frame.frame_id,
        "frame_id_origin": "per_eye_application_sequence",
        "sensor_timestamp_ns": frame.sensor_timestamp_ns,
        "exposure_time_us": frame.exposure_time_us,
        "host_received_monotonic_ns": frame.host_received_monotonic_ns,
        "timestamp_domain": frame.timestamp_domain,
        "image_size": list(frame.image_size),
        "pixel_format": frame.pixel_format,
        "metadata": frame.metadata,
    }


def save_pair(root: Path, pair: FramePair) -> Path:
    if not pair.valid or pair.left is None or pair.right is None:
        raise ValueError("只能儲存通過配對檢查的雙眼影像。")
    key = f"{pair.pair_id:06d}"
    record: dict[str, Any] = {
        "schema_version": 1,
        "pair_id": pair.pair_id,
        "valid": True,
        "delta_ms": pair.delta_ms,
        "synchronization_mode": pair.synchronization_mode,
        "saved_at_utc": utc_now(),
    }
    encoded = {}
    for side, frame in (("left", pair.left), ("right", pair.right)):
        ok, image = cv2.imencode(".png", frame.image_bgr)
        if not ok:
            raise ValueError(f"{side} PNG 編碼失敗。")
        data = image.tobytes()
        encoded[side] = data
        record[side] = eye_metadata(frame)
        record[side]["relative_path"] = f"{side}/{key}.png"
        record[side]["sha256"] = hashlib.sha256(data).hexdigest()
    paths = [root / side / f"{key}.png" for side in encoded]
    metadata_path = root / "metadata" / f"{key}.json"
    if any(path.exists() for path in [*paths, metadata_path]):
        raise FileExistsError(f"pair {key} 已存在，拒絕覆蓋。")
    # metadata 最後建立，表示本對寫入完成。失敗的殘留資料不自動刪除；
    # 離線載入會拒絕不完整資料集，請人工保留／檢查後再處理。
    for side, data in encoded.items():
        with (root / side / f"{key}.png").open("xb") as stream:
            stream.write(data)
    write_json_new(metadata_path, record)
    return metadata_path


def read_pair_files(
    left_path: Path, right_path: Path, metadata_path: Path
) -> tuple[np.ndarray, np.ndarray, dict]:
    record = json.loads(metadata_path.read_text(encoding="utf-8"))
    if record.get("schema_version") != 1 or record.get("valid") is not True:
        raise ValueError("影格 metadata 格式或有效旗標不符。")
    images = []
    for side, path in (("left", left_path), ("right", right_path)):
        eye = record[side]
        if (
            path.name != Path(eye["relative_path"]).name
            or file_hash(path) != eye["sha256"]
        ):
            raise ValueError(f"{side} 名稱／雜湊不符，可能左右相反或影像被改動。")
        image = cv2.imdecode(
            np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR
        )
        if image is None or image.size == 0:
            raise ValueError(f"{side} 影像損壞：{path}")
        if [image.shape[1], image.shape[0]] != eye["image_size"]:
            raise ValueError(f"{side} 尺寸與 metadata 不符。")
        images.append(image)
    if images[0].shape != images[1].shape:
        raise ValueError("左右影像尺寸不一致。")
    lt = record["left"]["sensor_timestamp_ns"]
    rt = record["right"]["sensor_timestamp_ns"]
    domain = record["left"]["timestamp_domain"]
    delta = record["delta_ms"]
    if (
        not isinstance(lt, int) or not isinstance(rt, int)
        or isinstance(lt, bool) or isinstance(rt, bool)
        or lt < 0 or rt < 0 or not domain
        or domain != record["right"]["timestamp_domain"]
        or not isinstance(delta, (int, float)) or not np.isfinite(delta)
        or delta < 0 or not np.isclose(abs(lt - rt) / 1e6, delta)
    ):
        raise ValueError("感測器時間或時間域無效。")
    return images[0], images[1], record


def load_calibration(path: Path) -> tuple[dict, dict[str, np.ndarray]]:
    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata_json"].item()))
        matrices = {
            key: archive[key].copy()
            for key in (*MATRIX_SHAPES, "D1", "D2")
        }
    if metadata.get("schema_version") != 1:
        raise ValueError("不支援的校正檔版本。")
    for key, shape in MATRIX_SHAPES.items():
        if matrices[key].shape != shape:
            raise ValueError(f"校正矩陣 {key} 尺寸錯誤。")
    for key, value in matrices.items():
        if not np.isfinite(value).all():
            raise ValueError(f"校正矩陣 {key} 含無效數。")
    for key in ("D1", "D2"):
        if matrices[key].size not in (4, 5, 8, 12, 14):
            raise ValueError(f"校正畸變係數 {key} 長度錯誤。")
    if not metadata.get("calibration_id"):
        raise ValueError("校正檔缺少 calibration_id。")
    if (
        metadata.get("translation_unit") != "mm"
        or np.linalg.norm(matrices["T"]) <= 0
    ):
        raise ValueError("校正單位不符或基線無效。")
    return metadata, matrices
