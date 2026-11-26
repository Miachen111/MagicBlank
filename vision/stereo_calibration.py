"""以實際棋盤影像做離線雙目校正；未執行或驗證。"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any
import uuid

import cv2
import numpy as np

from .calibration_data import read_pair_files, utc_now, write_json_new


def reprojection_errors(
    objects: list[np.ndarray],
    corners: list[np.ndarray],
    rvecs: tuple[np.ndarray, ...],
    tvecs: tuple[np.ndarray, ...],
    intrinsic: np.ndarray,
    distortion: np.ndarray,
) -> list[float]:
    errors = []
    for points, detected, rotation, translation in zip(
        objects, corners, rvecs, tvecs
    ):
        projected, _ = cv2.projectPoints(
            points, rotation, translation, intrinsic, distortion
        )
        error = np.sqrt(np.mean(np.sum(
            (detected.reshape(-1, 2) - projected.reshape(-1, 2)) ** 2,
            axis=1,
        )))
        errors.append(float(error))
    return errors


def calibrate(
    pairs_dir: Path,
    board_cols: int,
    board_rows: int,
    square_size_mm: float,
    output_path: Path,
    min_pairs: int = 10,
) -> dict:
    if (
        board_cols < 2 or board_rows < 2 or min_pairs < 3
        or not math.isfinite(square_size_mm) or square_size_mm <= 0
    ):
        raise ValueError("內角點至少 2×2，方格尺寸須正有限數，至少 3 對。")
    report_path = output_path.with_suffix(output_path.suffix + ".report.json")
    if output_path.exists() or report_path.exists():
        raise FileExistsError("校正輸出或報告已存在，拒絕覆蓋。")
    if not output_path.parent.is_dir():
        raise ValueError("輸出父目錄須先存在。")
    report: dict[str, Any] = {
        "schema_version": 1,
        "created_at_utc": utc_now(),
        "status": "failed",
        "board_inner_corners": [board_cols, board_rows],
        "square_size_mm": square_size_mm,
        "min_pairs": min_pairs,
        "pairs": [],
    }
    try:
        session = json.loads(
            (pairs_dir / "session.json").read_text(encoding="utf-8")
        )
        if session.get("schema_version") != 1:
            raise ValueError("採集 session 版本不符。")
        capture = session["capture"]
        groups = {}
        for folder, extension in (
            ("left", ".png"), ("right", ".png"), ("metadata", ".json")
        ):
            groups[folder] = {
                path.stem: path
                for path in (pairs_dir / folder).glob(f"*{extension}")
            }
        keys = set(groups["left"])
        if (
            not keys or keys != set(groups["right"])
            or keys != set(groups["metadata"])
        ):
            raise ValueError("左右 PNG 與 metadata 的 pair_id 不完整配對。")
        if any(not key.isdigit() for key in keys):
            raise ValueError("pair_id 檔名必須是數字。")
        board = (board_cols, board_rows)
        object_template = np.zeros((board_cols * board_rows, 3), np.float32)
        object_template[:, :2] = np.mgrid[
            0:board_cols, 0:board_rows
        ].T.reshape(-1, 2) * square_size_mm
        objects, left_points, right_points = [], [], []
        accepted = []
        image_size = None
        geometry = None
        for key in sorted(keys, key=int):
            item: dict[str, Any] = {"pair_id": key, "usable": False}
            report["pairs"].append(item)
            try:
                left, right, record = read_pair_files(
                    groups["left"][key], groups["right"][key],
                    groups["metadata"][key],
                )
                if record["pair_id"] != int(key):
                    raise ValueError("metadata pair_id 與檔名不符。")
                if record["delta_ms"] > capture["max_pair_delta_ms"]:
                    raise ValueError("時間差超過採集 session 門檻。")
                current_geometry = {}
                for side in ("left", "right"):
                    eye = record[side]
                    expected = capture["cameras"][side]["camera_id"]
                    if eye["camera_id"] != expected:
                        raise ValueError(f"{side} 相機 Id 與 session 不符。")
                    current_geometry[side] = eye["metadata"]["geometry"]
                    if (
                        current_geometry[side].get("main") is None
                        or current_geometry[side].get("scaler_crop") is None
                    ):
                        raise ValueError("缺少 main／ScalerCrop 幾何紀錄。")
                size = (left.shape[1], left.shape[0])
                if image_size is not None and size != image_size:
                    raise ValueError("影像尺寸不同於此資料集已接受的影像。")
                if geometry is not None and current_geometry != geometry:
                    raise ValueError("sensor mode／crop／transform 設定改變。")
                detected = []
                for image in (left, right):
                    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                    found, corners = cv2.findChessboardCornersSB(gray, board)
                    if not found or corners is None:
                        raise ValueError("至少一眼未找到完整棋盤內角點。")
                    if not np.isfinite(corners).all():
                        raise ValueError("棋盤角點含無效座標。")
                    detected.append(corners.astype(np.float32))
                image_size = size
                geometry = current_geometry
                objects.append(object_template.copy())
                left_points.append(detected[0])
                right_points.append(detected[1])
                item.update({
                    "usable": True,
                    "reason": None,
                    "left_file": record["left"]["relative_path"],
                    "right_file": record["right"]["relative_path"],
                    "metadata_file": f"metadata/{key}.json",
                    "left_sha256": record["left"]["sha256"],
                    "right_sha256": record["right"]["sha256"],
                })
                accepted.append(item)
            except (ValueError, KeyError, OSError, cv2.error) as exc:
                item["reason"] = str(exc)
        if len(objects) < min_pairs:
            raise ValueError(
                f"僅 {len(objects)} 對可用，至少需要 {min_pairs} 對；"
                "請補採不同位置／角度，勿以假矩陣填補。"
            )
        assert image_size is not None and geometry is not None
        rms1, k1, d1, rv1, tv1 = cv2.calibrateCamera(
            objects, left_points, image_size, None, None
        )
        rms2, k2, d2, rv2, tv2 = cv2.calibrateCamera(
            objects, right_points, image_size, None, None
        )
        rms, k1, d1, k2, d2, rotation, translation, _, _ = (
            cv2.stereoCalibrate(
                objects, left_points, right_points,
                k1, d1, k2, d2, image_size,
                criteria=(
                    cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                    100, 1e-6,
                ),
                flags=cv2.CALIB_FIX_INTRINSIC,
            )
        )
        r1, r2, p1, p2, q, roi1, roi2 = cv2.stereoRectify(
            k1, d1, k2, d2, image_size, rotation, translation,
            flags=cv2.CALIB_ZERO_DISPARITY, alpha=0,
        )
        matrices = {
            "K1": k1, "D1": d1, "K2": k2, "D2": d2,
            "R": rotation, "T": translation,
            "R1": r1, "R2": r2, "P1": p1, "P2": p2, "Q": q,
        }
        baseline = float(np.linalg.norm(translation))
        if (
            not all(np.isfinite(matrix).all() for matrix in matrices.values())
            or not all(math.isfinite(float(x)) for x in (rms1, rms2, rms))
            or baseline <= 0
            or min(k1[0, 0], k1[1, 1], k2[0, 0], k2[1, 1]) <= 0
        ):
            raise ValueError("求解產生非有限或退化結果，不輸出校正檔。")
        errors1 = reprojection_errors(
            objects, left_points, rv1, tv1, k1, d1
        )
        errors2 = reprojection_errors(
            objects, right_points, rv2, tv2, k2, d2
        )
        for index, item in enumerate(accepted):
            ul = cv2.undistortPoints(
                left_points[index], k1, d1, R=r1, P=p1
            )
            ur = cv2.undistortPoints(
                right_points[index], k2, d2, R=r2, P=p2
            )
            vertical = np.abs(ul[:, 0, 1] - ur[:, 0, 1])
            item.update({
                "left_reprojection_rms_px": errors1[index],
                "right_reprojection_rms_px": errors2[index],
                "rectified_vertical_mean_px": float(vertical.mean()),
                "rectified_vertical_max_px": float(vertical.max()),
            })
        metadata = {
            "schema_version": 1,
            "calibration_id": str(uuid.uuid4()),
            "created_at_utc": utc_now(),
            "image_size": list(image_size),
            "left_camera_id": capture["cameras"]["left"]["camera_id"],
            "right_camera_id": capture["cameras"]["right"]["camera_id"],
            "left_right_order": ["left", "right"],
            "geometry": geometry,
            "capture": capture,
            "board_inner_corners": list(board),
            "square_size_mm": square_size_mm,
            "translation_unit": "mm",
            "baseline_mm": baseline,
            "nominal_baseline_mm_for_comparison_only": 60.0,
            "baseline_to_nominal_ratio": baseline / 60.0,
            "rms_px": {"left": rms1, "right": rms2, "stereo": rms},
            "valid_roi_left": list(roi1),
            "valid_roi_right": list(roi2),
            "rectification_alpha": 0,
            "source_pairs": report["pairs"],
            "opencv_version": cv2.__version__,
            "validation_status": "fitted_only_not_independently_validated",
        }
        # 所有求解與序列化成功後才建立 NPZ；不 pickle SDK 物件。
        metadata_json = json.dumps(
            metadata, ensure_ascii=False, allow_nan=False
        )
        with output_path.open("xb") as stream:
            np.savez_compressed(
                stream, **matrices, metadata_json=np.array(metadata_json)
            )
        report.update({
            "status": "fitted_not_validated",
            "calibration_id": metadata["calibration_id"],
            "usable_pairs": len(objects),
            "rms_px": metadata["rms_px"],
            "baseline_mm": baseline,
        })
        write_json_new(report_path, report)
        return metadata
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        if not report_path.exists():
            write_json_new(report_path, report)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="離線雙目棋盤校正，輸出 NPZ")
    parser.add_argument("--pairs-dir", type=Path, required=True)
    parser.add_argument("--board-cols", type=int, required=True)
    parser.add_argument("--board-rows", type=int, required=True)
    parser.add_argument("--square-size-mm", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-pairs", type=int, default=10)
    args = parser.parse_args()
    try:
        result = calibrate(
            args.pairs_dir, args.board_cols, args.board_rows,
            args.square_size_mm, args.output, args.min_pairs,
        )
        print(
            f"校正擬合完成：{result['calibration_id']}；"
            f"baseline={result['baseline_mm']:.3f} mm；尚未獨立驗證。"
        )
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"校正失敗：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
