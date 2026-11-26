# MagicBlank 視覺模組｜A

目前已寫入單路追蹤及雙路接入／時間配對／棋盤校正工具草稿；依使用者指示，尚未安裝依賴、執行或測試。2026-11-24 使用者已確認 Pi 5 與 Waveshare IMX219-83 Stereo Camera；實機環境與新工具行為仍待驗證。

## 本次雙路與校正工具：先讀這裡

1. [CAMERA_SETUP.md](../docs/CAMERA_SETUP.md)：官方依據、人工接線與系統設定、相機列舉、左右 Id 確認及同步限制。
2. [STEREO_CALIBRATION.md](../docs/STEREO_CALIBRATION.md)：人工採集、棋盤參數、離線校正與獨立影像的校直檢視。
3. [DEPENDENCIES.md](DEPENDENCIES.md)：Pi apt 與本機離線依賴分流，不混裝多個 cv2。
4. 程式順序：`camera.py` 的 `StereoCamera` → `stereo_pairing.py` → `tools/capture_stereo_calibration.py` → `stereo_calibration.py` → `rectification_preview.py`；`calibration_data.py` 共用 PNG／JSON／NPZ 存取。

雙路資料流：每眼獨立 worker → 同 request 的 BGR／metadata → 有界感測器時間配對 → 人工採集 → K／D／R／T 求解 → 校直預覽。有效對與丟棄事件都使用 `FramePair`，無效事件不能進入採集或未來深度計算。

雙路預覽可用 `python -m vision.preview --stereo --mapping data/stereo_mapping.json`（預定指令，尚未實測）；不需要 MediaPipe 或模型。單路 `--pi`／`--video` 追蹤仍保留，`hand_tracker.py` 演算法未修改。

**同步模式固定為 `timestamp_pairing_only`**。IMX219-83 沒有硬體同步；時間差小不保證整張 rolling-shutter 影像曝光一致。官方軟體同步只寫入人工指南，本次 Python 不接入同步控制項。640×480／30fps／10ms 配對差等是可調工程起點，不是實測性能或精度。沒有 StereoSGBM、深度、桌面四角 ROI、桌面平面或觸碰判斷，也不新增設備控制。

以下保留原單路里程碑說明；其中單路限制不代表新增校正工具已通過驗證。**本次未安裝、未執行、未測試；未證明雙目深度或桌面接觸可行。**

建議拆成 camera.py、calibration.py、hand_tracker.py、depth.py、touch_detector.py、main.py；先按實際需求建立，不填入假實作。

未來整合階段的事件輸出須遵守 shared/PROTOCOL.md；本次只回傳內部影像 XY，不產生共用觸控事件。未來桌面平面與相機須使用相同座標系；深度必須與手部追蹤影像對齊。指尖可見表面的深度不等於實際接觸點，須實測補償與門檻。不要以固定深度常數假裝真實觸控。

校正板可作為開發時工具；正式操作區不依賴持續貼附標記。無紋理桌面與指尖邊界可能缺乏有效深度，實測前不保證可行。相機或桌面移動後重新校正。

原規劃的第一週交付包含擷取畫面、追蹤疊圖、接觸與懸空量測紀錄；本次僅撰寫單路 2D 追蹤草稿，尚無量測紀錄，也沒有加入模擬資料或事件輸出。

##  A，剛開始先讀哪些檔案

1. `camera.py`：定義單路 `FrameSource.open/read/close`，保留 Picamera2 與影片 adapter；新增雙路 `StereoCamera.open/read_pair/close`，只做時間配對，不包含 USB webcam adapter。
2. `hand_tracker.py`：用 MediaPipe Tasks 取食指 Landmark 8，只回傳影像 XY。
3. `preview.py`：把影像與追蹤串起來，畫出指尖；按 Q 或 Esc 結束。

原第一個小目標是「畫面中看得到食指指尖標記」。本次擴充至雙路接入與校正草稿，仍沒有雙目曝光同步、深度、桌面映射、觸控或 MQTT，不能稱為完整 A 模組。依使用者要求，先理解與修改程式，不執行下列步驟。

## 之後恢復執行時的準備（現在不用操作）

最終執行主板已確認為 **Raspberry Pi 5**。根目錄既有 D001 仍記錄筆電視覺的早期預設；這次依目前需求準備 Pi 5 路徑，不代表已確認 Pi 的效能、相機相容性或完成部署。

以下僅供之後準備，**本次未安裝、未執行、未測試，尚未執行或驗證；未做硬體實測**。

- 系統層：先確認 Raspberry Pi OS 版本、位元架構與 Python 版本。Pi 路徑需要該系統相容的 Picamera2、libcamera 與相機驅動；常見系統套件名稱是 `python3-picamera2`、`python3-libcamera`，實際可用性須依 OS 確認，不以 pip 清單取代系統安裝。
- Python 層：`numpy` 處理影像陣列、`mediapipe` 提供 Tasks Hand Landmarker、OpenCV 提供影片解碼與疊圖。`requirements-vision.txt` 是未驗證的候選清單，未鎖定版號；先確認 Pi 5 的 OS／Python／架構有相容的 MediaPipe 套件，再記錄成功環境，不保證 pip 能直接取得 Pi 可用版本。
- OpenCV 只保留一個提供 `cv2` 的來源。清單選 `opencv-contrib-python`，以配合部分 MediaPipe 版本的相依需求；本程式只用基本 cv2 API。不要另裝 `opencv-python` 或 headless 變體。若 Pi 使用系統 `python3-opencv`，須先調整候選清單及確認 MediaPipe 相依解析不會再帶入 pip OpenCV，再安裝其餘依賴，避免混用。尚未選定套件版本，這個系統版替代路徑也未驗證。
- 虛擬環境：之後在專案根目錄建立；Pi 的系統 Picamera2／libcamera 通常需讓環境可見系統套件（例如建立環境時使用 `--system-site-packages`）。須確認系統與虛擬環境使用的 Python 相容，不能假定任意 Python 版本都可匯入系統綁定。
- 模型：之後自行從 [官方 MediaPipe Hand Landmarker 頁面](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker?tab=Python) 取得相容的 `hand_landmarker.task`，例如放在 `models/`，保存來源與授權。程式不會下載模型；模型與影片不提交 Git。模型路徑由 `--model` 明確指定。
- 顯示：視窗模式需要桌面環境及可用的 OpenCV GUI 後端；純 SSH／無桌面時使用 `--no-window`。此模式仍做影像追蹤，但只輸出文字，不會呼叫視窗 API，也不自動儲存影像。

預定指令（**尚未實測**），皆從專案根目錄執行；尺寸與幀率是請求設定，不是已驗證的硬體規格或效能：

```bash
python -m vision.preview --pi --camera-index 0 --model models/hand_landmarker.task --width 640 --height 480 --fps 30
# 本機影片，輸入後縮放為指定大小（比例不同時可能變形）：
python -m vision.preview --video data/hand_sample.mp4 --model models/hand_landmarker.task --width 640 --height 480
# 不開視窗；Ctrl+C 結束，影片確認結束時也會退出：
python -m vision.preview --video data/hand_sample.mp4 --model models/hand_landmarker.task --no-window
```

執行時若相機編號不符、缺模型或套件不相容，須在恢復驗證階段處理；本次未確認能在你的電腦直接執行。相機畫面的 x/y 不等於桌面 x/y；此程式未計算或利用 MediaPipe z 判斷觸碰。

## 影像如何流動

`camera.read()` → `Frame.image_bgr` → `HandTracker.track()` → `HandTrackingResult` → `preview.py` 疊圖或文字輸出。

- `camera.py` 統一輸出三通道 BGR、由 0 開始的 `frame_id`、來源與主機 `monotonic_ns` 時間。時間記錄在取得影像後，不是曝光時間，也不是 Unix 時間，不能直接作為 shared 協定的 `timestamp_ms`。來源重新開啟後幀號重設。影片由 OpenCV 解碼為 BGR；Pi 選用 Picamera2 `RGB888`，其陣列依 libcamera 命名慣例為 BGR 位元組，仍須實機用色卡確認。
- Pi 若實際提供 `SensorTimestamp`，會額外保留原始值與來源；未確認其驅動時間域，不和主機時間混算，也不宣稱已同步。影片的 `video_position_ms_raw` 是 OpenCV 解碼器回報的媒體位置，可能不可用；不是曝光時間。
- `hand_tracker.py` 將 BGR 轉為 RGB 後送入 MediaPipe Tasks VIDEO 模式，只追蹤單手並取 Landmark 8。不保留全部 landmarks、world landmarks、Z 或 handedness 分數。
- VIDEO 時間戳使用 tracker 建立後的主機經過毫秒，每次至少比上次增加 1；這是處理排程時間，與原始擷取時間、感測器時間及影片媒體時間分開。影片目前盡快處理，不按原始幀率播放，因此時間戳不代表原影片節奏。
- 結果是 `image_xy_normalized` 與 `image_xy_pixels`。正規化影像原點在左上，x 向右、y 向下；像素位置依當前輸入尺寸計算。沒有手、指尖不在畫面內或座標無效時，`hand_detected=False`、兩種 XY 皆為 `None`；不沿用舊位置。這裡的旗標表示有可用的畫面內指尖，並非觸碰信心分數。
- `preview.py` 不改 shared 事件格式，不發事件。顯示 `2D PREVIEW - NO DEPTH / NO TOUCH`、影像 XY 或 `Tracking lost`。視窗按 Q／Esc 結束；Ctrl+C 或錯誤時也走資源釋放路徑。這些路徑尚未執行驗證。

## 來源失敗與資源

`open()` 失敗拋 `SourceOpenError`；開啟後讀取失敗拋 `SourceReadError`。Pi 不會以 `None` 假裝讀取成功或影片結束。Picamera2 僅在開啟 Pi 來源時才匯入，缺少它不影響影片 adapter 的匯入。

影片只有在讀取失敗且已讀完容器回報的幀數時才回傳 `None` 表示 EOF。OpenCV 無法普遍區分 EOF 與解碼錯誤；幀數未知／不準或影片損壞時，本草稿保守回報錯誤，不默默當成正常結束。仍需日後用實際影片驗證解碼器行為。

來源與 tracker 提供 `close()` 及 context manager；Pi request 的影像複製後即釋放 request，離開預覽時釋放來源與模型，視窗模式另關閉視窗。未提供讀取逾時或卡住的硬體驅動復原機制，實機階段再依 SDK 行為確認。

## 為何影像 XY 不能判斷桌面觸碰

影像 XY 只是食指尖在相機畫面的位置，受相機角度、透視、鏡頭與影片縮放影響。它沒有桌面範圍、方向與公制尺度，也沒有經過校正，所以不能直接填入 shared 協定要求的桌面 XY。畫面相同位置可能對應懸空或接觸的手指，單靠 2D XY 無法判斷是否碰到桌面。

MediaPipe 的相對 Z 與 world landmarks 也不是已校正的離桌毫米高度。本次已新增離線雙目校正工具草稿，但沒有產生實際校正結果，也沒有 StereoSGBM、桌面平面、深度估計、觸碰判斷、MQTT、網頁或 LED／Servo 控制。

## 相機與後續待確認資訊

Picamera2 adapter 是**預備支援路徑**，不表示現有雙目相機必然受支援。`--camera-index 0` 只代表 SDK 枚舉編號，不等於左眼；也沒有開啟兩個來源就稱為同步雙目。

已收到相機型號與官方資料，不再要求重複提供型號：

- [Waveshare 官方產品頁](https://www.waveshare.com/product/raspberry-pi/boards-kits/imx219-83-stereo-camera.htm) 列出 IMX219-83 Stereo Camera 及 Raspberry Pi 5 支援。
- [Waveshare 官方 Wiki](https://www.waveshare.com/wiki/IMX219-83_Stereo_Camera) 列出 CSI 介面、Pi 5 連接及 libcamera 使用方式，並提及 Picamera2。這是單路 adapter 的文件依據，不代表本專案已完成實機驗證。查閱日期：2026-11-24；直接讀取網頁受 403 限制，本次依官方頁面的搜尋索引內容核對。
- 官方列有兩路相機的個別選取方式，不能因此認定兩路已同步曝光。新增的雙路工具核對左右 index 與 Id，提供時間配對；沒有新增深度功能。

接下來仍需確認實際接線／線材、Pi 5 RAM、預定 OS／Python 版本、裝置枚舉與左右身分，以及可用的擷取模式、同步與時間戳語意、校正資料。本次不設定驅動或接觸硬體。使用者另提供專案技術規格書 PDF，但本回合文件視窗讀取工具停止，尚未讀取其內容；不將規格書內的假設當成已確認成果。

## VS Code Problems 的判讀

Problems 不一定都代表同一種問題，請依完整訊息區分：

- `reportMissingImports`／`reportMissingModuleSource`：可能是目前 VS Code 選用的 Python 環境沒有套件，或缺少套件來源資訊。本次依要求未安裝套件，因此不能宣稱匯入診斷已清除。Pi 專用 Picamera2 不應靠在 Windows 硬裝系統綁定解決。
- 座標型別問題：原本只檢查 `hand_detected` 就解包可能為 `None` 的 XY，型別檢查器無法推論兩者關係。已改成明確檢查 XY 非 `None`，並為兩種來源共同變數標示 `FrameSource` 型別；尚未執行靜態檢查確認診斷結果。
- 其他錯誤須依 Problems 的檔名、行號、錯誤代碼與訊息逐項修正；本次沒有用關閉診斷或假造 SDK 模組來隱藏問題，也尚未取得完整清單。

恢復驗證後先確認依賴與模型可載入、影片／Pi 色彩與尺寸、正常 EOF／讀取錯誤／追蹤遺失、Q／Esc／Ctrl+C 資源釋放，再確認 Pi 5 的實際幀率。AI 修改需由另一位組員審查；本次沒有執行測試或協定檢查，亦未做硬體實測。

## 接下來的 A 開發順序

影像輸入 → 食指 XY → 追蹤遺失 → 雙路擷取／配對 → 棋盤採集／離線校正 → 獨立校直檢視 → 日後才考慮深度、桌面平面與觸控。前三項保留原程式，本次完成中間工具草稿，尚無任何執行或硬體驗證；未來原圖與校直圖的座標不能混用。
