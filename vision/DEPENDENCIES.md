# 視覺依賴分流（尚未安裝或驗證）

| 工作 | 系統相依 | Python 模組 |
| --- | --- | --- |
| Pi 雙路／校正採集 | Pi OS 原生 imx219、libcamera、Picamera2 | cv2、numpy |
| 離線校正／校直 | 不需相機驅動；視窗需 GUI | cv2、numpy |
| 原有單路食指追蹤 | Pi 來源才需 Picamera2 | cv2、numpy、mediapipe |

本次雙路工具不需要安裝 MediaPipe，也不下載模型。Python 標準庫負責
threading、JSON、雜湊與檔案存取，沒有新增第三方配對或校正框架。
新增 Pi 工具以 Python 3.11 以上語法／例外 API 為撰寫基準；Pi 實際版本
仍待確認，不因 Windows 使用 3.14.6 就要求 Pi 改用同版 Python。

Pi 優先使用 apt 的 `python3-picamera2 python3-opencv python3-numpy
python3-venv`，搭配 `--system-site-packages`；完整人工指令與驅動限制見
[CAMERA_SETUP.md](../docs/CAMERA_SETUP.md)。不要為了 Windows 匯入警告
嘗試硬裝 Pi 系統綁定，也不要混裝多個提供 cv2 的發行包。

Windows 本機已由使用者確認 Python 3.14.6／`C:\Python314\python.exe`。
離線工具依賴可先參考根目錄 `requirements-calibration.txt`；這是候選清單，
未驗證其平台版本組合，不是目前已可執行環境。Pi 若已有 apt OpenCV，
不要再安裝該 pip 清單。

根目錄 `requirements-vision.txt` 保留原有食指追蹤的候選依賴；
它與 `requirements-calibration.txt` 是不同用途的環境選項，**不要在同一
環境同時安裝兩份**。若日後合併需求，先決定唯一 cv2 來源並核對 MediaPipe
相依；不能把未測的套件清單當作可重現環境。

恢復驗證後記錄 Pi OS／架構／Python、Picamera2、libcamera、rpicam、
OpenCV、NumPy 實際成功版本。現在不捏造精確版本，也不執行安裝或查版號。
