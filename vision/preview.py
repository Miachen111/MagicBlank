"""從專案根目錄以 python -m vision.preview 啟動；本草稿尚未執行或驗證。"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import math
from pathlib import Path
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MagicBlank 單路追蹤／雙路時間配對預覽，無深度／觸控辨識"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pi", action="store_true", help="預備的 Picamera2 單路來源")
    source.add_argument("--video", type=Path, help="本機影片路徑")
    source.add_argument(
        "--stereo", action="store_true", help="雙路時間配對預覽，無深度"
    )
    parser.add_argument("--mapping", type=Path, help="人工確認的左右 Id 設定")
    parser.add_argument("--max-pair-delta-ms", type=float, default=10.0)
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="SDK 相機編號，不代表左右身分",
    )
    parser.add_argument(
        "--model",
        type=Path,
        help="Hand Landmarker .task 模型",
    )
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument(
        "--fps", type=float, default=30.0, help="Pi 目標幀率，非實測效能"
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="不開視窗，逐幀輸出 XY；Ctrl+C 結束",
    )
    args = parser.parse_args()
    if args.width <= 0 or args.height <= 0 or args.camera_index < 0:
        parser.error("影像尺寸須為正數，camera index 須非負。")
    if not math.isfinite(args.fps) or args.fps <= 0:
        parser.error("fps 須為正有限數。")
    if args.stereo and args.mapping is None:
        parser.error("stereo 須提供 mapping。")
    if not args.stereo and args.model is None:
        parser.error("單路追蹤須提供 model。")
    return args


def run_stereo(args: argparse.Namespace) -> int:
    """原始雙眼的時間配對預覽；不匯入 MediaPipe，不估計深度。"""
    import cv2
    import numpy as np

    from .camera import StereoCamera

    print("Stereo preview: timestamp_pairing_only / NO DEPTH / NO TOUCH")
    with StereoCamera(
        args.mapping, args.width, args.height, args.fps,
        args.max_pair_delta_ms,
    ) as camera:
        while True:
            pair = camera.read_pair()
            if not pair.valid:
                print(f"丟棄：{pair.discard_reason}", flush=True)
                continue
            assert pair.left is not None and pair.right is not None
            assert pair.delta_ms is not None
            label = f"pair={pair.pair_id} delta={pair.delta_ms:.3f} ms"
            if args.no_window:
                print(label, flush=True)
                continue
            image = np.hstack((pair.left.image_bgr, pair.right.image_bgr))
            cv2.putText(
                image, label, (10, 24), cv2.FONT_HERSHEY_SIMPLEX,
                0.6, (0, 255, 255), 1,
            )
            cv2.putText(
                image, "PAIRING ONLY - NO DEPTH / NO TOUCH", (10, 48),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1,
            )
            cv2.imshow("Stereo raw left / right - Q Esc exit", image)
            if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                break
    return 0


def main() -> int:
    args = parse_args()
    cv2 = None
    try:
        import cv2
        if args.stereo:
            return run_stereo(args)
        from .camera import FrameSource, Picamera2Source, VideoFileSource
        from .hand_tracker import HandTracker

        source: FrameSource
        if args.pi:
            source = Picamera2Source(
                args.camera_index, args.width, args.height, args.fps
            )
        else:
            source = VideoFileSource(args.video, args.width, args.height)
        print("2D preview：僅影像 XY，尚未進行深度與觸控辨識。", flush=True)
        with ExitStack() as stack:
            tracker = stack.enter_context(HandTracker(args.model))
            source = stack.enter_context(source)
            while True:
                frame = source.read()
                if frame is None:
                    print("本機影片結束。", flush=True)
                    break
                result = tracker.track(frame.image_bgr)
                image_xy = result.image_xy_normalized
                pixel_xy = result.image_xy_pixels
                # bool 欄位不能讓型別檢查器推知其他欄位一定不是 None。
                # 直接檢查區域變數，才可安全解包 optional 座標。
                if (
                    result.hand_detected
                    and image_xy is not None
                    and pixel_xy is not None
                ):
                    x, y = image_xy
                    px, py = pixel_xy
                    label = f"Image XY: ({x:.3f}, {y:.3f}) / px ({px}, {py})"
                else:
                    label = "Tracking lost (no valid fingertip)"
                if args.no_window:
                    print(
                        f"frame={frame.frame_id} | 2D preview | {label}",
                        flush=True,
                    )
                    continue
                image = frame.image_bgr.copy()
                if result.image_xy_pixels is not None:
                    cv2.circle(
                        image, result.image_xy_pixels, 8, (0, 255, 0), 2
                    )
                # OpenCV 預設字型不支援中文，疊圖使用英文。
                cv2.putText(
                    image,
                    "2D PREVIEW - NO DEPTH / NO TOUCH",
                    (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 255),
                    1,
                )
                cv2.putText(
                    image,
                    label,
                    (10, 48),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (0, 255, 255),
                    1,
                )
                cv2.imshow("MagicBlank 2D preview - Q / Esc to exit", image)
                if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                    break
        return 0
    except KeyboardInterrupt:
        print("已中斷 2D 預覽。", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"2D 預覽失敗：{exc}", file=sys.stderr)
        return 1
    finally:
        if cv2 is not None and not args.no_window:
            try:
                cv2.destroyAllWindows()
            except Exception as exc:
                print(f"視窗釋放失敗：{exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
