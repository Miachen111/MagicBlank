# Raspberry Pi 5 雙目相機接入草稿

**本次未安裝、未執行、未測試，未存取相機；所有指令留待人工操作。**
Windows 可以編輯程式；以下相機、apt 與 `/boot` 操作只能在確認過的 Pi
環境進行。Windows 已確認使用 Python 3.14.6，不代表 Pi 的 Python 版本。

## 目標與依據

目標為 Raspberry Pi 5 + Waveshare IMX219-83 Stereo Camera（SKU 17742）。
下表是產品標稱資訊，不是這組實物的量測結果，也不是校正參數：

| 項目 | 產品標稱 |
| --- | --- |
| 感測器 | 雙 Sony IMX219 |
| 每眼解析度 | 3280 × 2464 |
| 焦距／光圈 | 2.6 mm／F2.4 |
| 視角（對角／水平／垂直） | 83°／73°／50° |
| 基線 | 60 mm |
| 連接 | CSI，Pi 5 需相容的 22-pin 線材 |

官方產品頁列出 Pi 5 支援；Waveshare FAQ 表示沒有硬體同步。
先後啟動兩眼不等於同步曝光，標稱視角也不能直接生成正式 K／D／R／T／Q。
不要把 Wiki 內其他型號的 IMX477／12MP／4056×3040 範例視為本機模式；
不要搬用 Jetson 的 `nvarguscamerasrc` 或 GStreamer 驅動路徑。

官方來源（2026-11-24；文件內容仍須與日後實際安裝版本對照）：

- [Waveshare 產品頁](https://www.waveshare.com/product/raspberry-pi/boards-kits/imx219-83-stereo-camera.htm)
- [Waveshare Wiki／FAQ](https://www.waveshare.com/wiki/IMX219-83_Stereo_Camera)
- [Raspberry Pi 相機與同步文件](https://www.raspberrypi.com/documentation/accessories/camera-software.html)
- [Picamera2 官方手冊](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf)
- [Picamera2 repository](https://github.com/raspberrypi/picamera2)

Waveshare 網頁直接讀取受 403 限制；型號資訊由使用者提供的開發依據與
官方搜尋索引交叉參照。Pi 文件、Picamera2 手冊與原始碼有線上查閱。
沒有替使用者執行任何接線、安裝、設定或相機指令。

## 接線：完全斷電後才做

將兩路 CSI 分別接到 Pi 5 的 CAM/DISP0、CAM/DISP1，依這個型號的官方圖
確認線材、接頭及接點方向。不可只憑藍色補強片顏色猜朝向。不要使用普通
相機切換板取代兩路同時擷取。保存實體左右定義及安裝方向的紀錄。

## 人工檢查系統與驅動

使用 Raspberry Pi OS 原生 imx219、libcamera／rpicam、Picamera2。
不使用 legacy Picamera／raspivid，也不啟用 legacy camera stack。

之後先人工查 OS：

```bash
cat /etc/os-release
```

現代 Raspberry Pi OS 的設定路徑是 `/boot/firmware/config.txt`。
先檢查既有 `camera_auto_detect`、overlay 與 `[all]` 等條件區段，再備份；
依實際 OS 與設定內容判斷是否需要修改。以下是**人工檢查並套用的範例**，
不是現在應自動附加的內容，也不是已讀取 Pi 設定所得的結果：

```ini
camera_auto_detect=0
dtoverlay=imx219,cam0
dtoverlay=imx219,cam1
```

Waveshare 提供兩路 overlay；Pi 官方的手動 overlay 說明要求停用自動偵測。
備份後由人編輯，避免重複設定或放入錯誤條件區段；完成後才人工 reboot。
本工具不寫 `/boot`、不自動重啟，也不推測目前的 OS。

## 之後的安裝與列舉

下列均為**尚未執行或驗證**的人工指令：

```bash
sudo apt update
sudo apt install python3-picamera2 python3-opencv python3-numpy python3-venv
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
rpicam-hello --list-cameras
rpicam-hello --camera 0 -t 5000
rpicam-hello --camera 1 -t 5000
```

實際 apt 版本與是否需要另裝 `rpicam-apps`，待恢復操作時確認。
不把 `pip install picamera2` 當成修好所有 libcamera 相依問題的方法。
此階段只需要 NumPy、OpenCV 及 Pi 系統 Picamera2，不需要 MediaPipe 模型。
不要同時裝系統 cv2、`opencv-python`、contrib 與 headless 等多個發行包。
`requirements-vision.txt` 保留給既有單路手部追蹤環境，不要直接覆蓋 Pi
的 apt 環境；詳見 `vision/DEPENDENCIES.md`。

## 保存左右身分，不只記 camera 0／1

從專案根目錄，在 Pi 人工執行資訊工具（會開啟相機物件以查詢資訊，
不啟動串流；本次沒有執行）：

```bash
python -m tools.camera_info --output data/camera-info.json
```

先人工建立 `data/`。工具輸出 `global_camera_info()` 的 Model、Id 等欄位，
以及每眼 `sensor_modes`、`camera_properties`、`camera_controls`；
檔案存在時拒絕覆蓋，不預填任何實測數字。

使用前述單眼預覽，人工遮住一顆鏡頭，確認哪個畫面被遮住；記錄以實體
安裝方向定義的 left/right。將 `vision/config/stereo_mapping.example.json`
複製為 `data/stereo_mapping.json`，填入實際 Id、索引與安裝說明：

```json
{
  "left": {"index": 0, "camera_id": "請填實際左眼 Id"},
  "right": {"index": 1, "camera_id": "請填實際右眼 Id"},
  "mounting_description": "請填安裝方向、遮鏡確認日期與操作者"
}
```

上面的 0／1 僅示例，不是左右身分保證。每次 `StereoCamera.open()` 都核對
index、Id 與 IMX219 Model；不符即拒絕開啟，不偷偷交換兩眼或按排序猜測。
重新插線、枚舉變化或相機交換時，須重新人工確認並更新設定；校正資料
的左右定義必須一致。

## 雙路擷取與配對預覽

```bash
python -m vision.preview --stereo --mapping data/stereo_mapping.json \
  --width 640 --height 480 --fps 30 --max-pair-delta-ms 10
```

加 `--no-window` 會只印有效影格對的 id／時間差與丟棄原因，用 Ctrl+C 結束。
視窗模式需桌面與 OpenCV GUI，Q／Esc 結束。640×480、30fps 是可改的
開發請求，不是已驗證模式；實際 sensor mode、crop、transform 與 controls
在採集 session 中保存。若 SDK 改變請求的輸出尺寸／格式則拒絕繼續。

每眼 worker 使用同一 `CompletedRequest` 取得影像與 metadata；複製後
在 `finally` 釋放 request。`RGB888` 的 Python 陣列是 BGR；`BGR888` 則是
RGB，不依名稱直覺再轉一次。frame_id 為每眼程式序號；SensorTimestamp
是開機時間域的感測器讀出時間，接近首像素讀出，不能直接稱為曝光起點。
ExposureTime 單位是微秒；host monotonic 另存，不作感測器時間替代。
程式以同一 Pi 的 boot id 標示時間域，跨 Pi／跨開機不可直接配對。

有界佇列及最近鄰選擇是**專案工程設計**，不是硬體同步：每眼佇列預設 6，
配對時間差預設 10ms，主機收件後最大等待年齡預設 500ms，均為待調參數。
在兩眼目前視窗選時間最近的一對，不等待未知未來幀；選中之前的舊幀丟棄，
每張只用一次，沒有符合門檻的候選時丟較舊影格。
這不是離線全域最佳匹配，時間接近不保證 rolling-shutter 全畫面曝光一致。
缺時間戳、時間域不符、序號時間倒退、溢位及過期都有丟棄事件；
`FramePair.valid=False` 的影格不能存成校正樣本或送進未來深度計算。
丟棄事件含可用一眼、時間與原因；不存在的另一眼／delta 為 None。
事件佇列也有上限；完整累計數在 pairer 的 `discard_counts`，不代表逐筆
事件永遠保留。擷取／配對逾時視為錯誤，不輸出假配對。

worker 使用官方非同步 request job 與有限等待，退出時取消待辦並釋放
request，主流程再關閉兩眼。已寫入部分開啟失敗與 Ctrl+C 的清理路徑，
但沒有執行驗證；若底層驅動本身阻塞，Python 無法保證強制中止它，
清理失敗會回報，須在實機階段處理。不要把有 timeout 當成已驗證復原。

## 軟體同步：本次只提供人工指南

Raspberry Pi 官方提供 server/client 幀時序調整，取決於安裝版本與
驅動的 frame-duration control。之後先確認 `rpicam-vid --help` 是否有
`--sync`；相同相機不要同時被本 Python 工具占用。

先在一個終端機啟動 client：

```bash
rpicam-vid -n -t 20s --camera 1 --codec libav -o client.mp4 --sync client
```

再在另一個終端機啟動 server：

```bash
rpicam-vid -n -t 20s --camera 0 --codec libav -o server.mp4 --sync server
```

這是官方軟體同步錄影方式，不表示本 Python 程式已同步。兩眼使用相同
目標幀率，低於該模式極限，保留縮短 frame duration 的調整餘裕。
時間戳配對、軟體調整幀時序、硬體曝光同步是三件不同的事。

查閱時新版手冊已有同步相關 controls，但尚未知道實機安裝版本／支援
狀態，因此本次不接入 Picamera2 同步 API，也不硬塞 `SyncMode` 等設定。
目前固定記錄 `synchronization_mode=timestamp_pairing_only`；日後另行核對
實際 API、controls 與 ready 狀態後才整合，並繼續保留配對及掉幀檢查。
ISP tuning JSON 是影像處理設定，不是雙目幾何校正檔。
