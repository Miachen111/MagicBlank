"""人工啟動的 Pi 相機資訊工具；不啟動影像串流。"""

import argparse
import json
from pathlib import Path

from vision.camera import json_value, load_picamera2


def main() -> None:
    parser = argparse.ArgumentParser(description="列舉 Pi 相機與 SDK 資訊")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    picamera2 = load_picamera2()
    infos = picamera2.global_camera_info()
    result = {"global_camera_info": json_value(infos), "cameras": []}
    for index, info in enumerate(infos):
        camera = picamera2(camera_num=index)
        try:
            result["cameras"].append({
                "index": index,
                "info": json_value(info),
                "sensor_modes": json_value(camera.sensor_modes),
                "camera_properties": json_value(camera.camera_properties),
                "camera_controls": json_value(camera.camera_controls),
            })
        finally:
            camera.close()
    text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
