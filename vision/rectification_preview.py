"""核對影像來源與校正設定後預覽校直；不做深度估計。"""

import argparse
from pathlib import Path
import sys

import cv2
import numpy as np

from .calibration_data import load_calibration, read_pair_files


def main() -> int:
    parser = argparse.ArgumentParser(description="離線校直前後對照，無深度")
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--pair-metadata", type=Path, required=True)
    parser.add_argument("--no-window", action="store_true")
    parser.add_argument("--output", type=Path, help="人工指定才儲存對照 PNG")
    args = parser.parse_args()
    try:
        if args.no_window and args.output is None:
            parser.error("no-window 須指定 output，才能檢視校直對照。")
        metadata, matrices = load_calibration(args.calibration)
        left, right, pair = read_pair_files(
            args.left, args.right, args.pair_metadata
        )
        if metadata["left_right_order"] != ["left", "right"]:
            raise ValueError("校正檔左右順序不符。")
        size = (left.shape[1], left.shape[0])
        if list(size) != metadata["image_size"]:
            raise ValueError("輸入尺寸與校正尺寸不符，拒絕自動縮放。")
        rectified = []
        for side, number, image in (("left", 1, left), ("right", 2, right)):
            eye = pair[side]
            if (
                eye["camera_id"] != metadata[f"{side}_camera_id"]
                or eye["metadata"]["geometry"] != metadata["geometry"][side]
            ):
                raise ValueError(f"{side} 相機或幾何設定與校正不符。")
            map_x, map_y = cv2.initUndistortRectifyMap(
                matrices[f"K{number}"], matrices[f"D{number}"],
                matrices[f"R{number}"], matrices[f"P{number}"],
                size, cv2.CV_32FC1,
            )
            rectified.append(cv2.remap(
                image, map_x, map_y, cv2.INTER_LINEAR
            ))
        raw = np.hstack((left, right))
        fixed = np.hstack(rectified)
        for canvas in (raw, fixed):
            for y in range(40, size[1], 40):
                cv2.line(canvas, (0, y), (2 * size[0] - 1, y), (0, 255, 0))
        canvas = np.vstack((raw, fixed))
        label = f"{metadata['calibration_id']} | {size[0]}x{size[1]}"
        cv2.putText(
            canvas, label, (8, 22), cv2.FONT_HERSHEY_SIMPLEX,
            0.5, (0, 255, 255), 1,
        )
        print(f"calibration={label}；上：原圖，下：校直。水平線不代表驗證通過。")
        if args.output:
            if args.output.suffix.lower() != ".png":
                raise ValueError("output 必須使用 .png。")
            ok, encoded = cv2.imencode(".png", canvas)
            if not ok:
                raise ValueError("對照 PNG 編碼失敗。")
            with args.output.open("xb") as stream:
                stream.write(encoded.tobytes())
        if not args.no_window:
            cv2.imshow("Raw (top) / rectified (bottom) - Q Esc exit", canvas)
            while cv2.waitKey(50) & 0xFF not in (ord("q"), ord("Q"), 27):
                pass
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"校直預覽失敗：{exc}", file=sys.stderr)
        return 1
    finally:
        if not args.no_window:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    raise SystemExit(main())
