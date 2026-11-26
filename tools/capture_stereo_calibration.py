"""人工觸發的棋盤影像採集；不做自動錄影或觸碰判斷。"""

import argparse
import math
from pathlib import Path
import sys
import time

import cv2
import numpy as np

from vision.calibration_data import save_pair, utc_now, write_json_new
from vision.camera import StereoCamera


def main() -> int:
    parser = argparse.ArgumentParser(description="人工採集已配對的雙眼 PNG")
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--max-pair-delta-ms", type=float, default=10.0)
    parser.add_argument("--max-save-age-ms", type=float, default=500.0)
    parser.add_argument("--no-window", action="store_true")
    args = parser.parse_args()
    if not math.isfinite(args.max_save_age_ms) or args.max_save_age_ms <= 0:
        parser.error("max-save-age-ms 須為正有限數。")
    try:
        # 新 session 目錄必須不存在，不續寫或覆蓋舊採集。
        args.output.mkdir(parents=True, exist_ok=False)
        for name in ("left", "right", "metadata"):
            (args.output / name).mkdir()
        with StereoCamera(
            args.mapping, args.width, args.height, args.fps,
            args.max_pair_delta_ms,
        ) as camera:
            write_json_new(args.output / "session.json", {
                "schema_version": 1,
                "created_at_utc": utc_now(),
                "capture": camera.session_info,
            })
            while True:
                triggered_ns = None
                if args.no_window:
                    answer = input("棋盤停穩後按 Enter 採一對；q 結束：")
                    if answer.strip().lower() == "q":
                        break
                    triggered_ns = time.monotonic_ns()
                deadline = time.monotonic() + camera.timeout_s
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("期限內沒有可採集的有效影格對。")
                    pair = camera.read_pair(timeout_s=remaining)
                    if not pair.valid:
                        print(f"丟棄：{pair.discard_reason}", flush=True)
                        continue
                    assert pair.left is not None and pair.right is not None
                    oldest = min(
                        pair.left.host_received_monotonic_ns,
                        pair.right.host_received_monotonic_ns,
                    )
                    if triggered_ns is not None and oldest < triggered_ns:
                        continue
                    break
                assert pair.left is not None and pair.right is not None
                assert pair.delta_ms is not None
                label = f"pair={pair.pair_id} delta={pair.delta_ms:.3f} ms"
                if args.no_window:
                    print(label)
                    save = True
                else:
                    canvas = np.hstack((
                        pair.left.image_bgr, pair.right.image_bgr
                    ))
                    cv2.putText(
                        canvas, label, (10, 24), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (0, 255, 255), 1,
                    )
                    cv2.imshow(
                        "Stereo capture: Space save / Q Esc exit", canvas
                    )
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("q"), ord("Q"), 27):
                        break
                    save = key == 32
                if save:
                    age_ms = (time.monotonic_ns() - oldest) / 1e6
                    if age_ms > args.max_save_age_ms:
                        print("影格對過期，請重新觸發。", flush=True)
                        continue
                    path = save_pair(args.output, pair)
                    print(f"已保存：{path} | {label}", flush=True)
        return 0
    except (KeyboardInterrupt, EOFError):
        return 130
    except Exception as exc:
        print(f"採集失敗：{exc}", file=sys.stderr)
        return 1
    finally:
        if not args.no_window:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    raise SystemExit(main())
