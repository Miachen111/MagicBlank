# 雙目採集、離線校正與校直預覽

**程式草稿尚未安裝、執行或測試；未做硬體實測。**
本階段不產生視差、深度或桌面觸碰結果。先讀
[相機接入指南](CAMERA_SETUP.md)，完成系統與左右身分的人工確認後，
才能在之後操作本文件。所有指令均為預定指令，現在不執行。

## 工具與資料流

`StereoCamera` 雙 worker → `TimestampPairer` → 有效 `FramePair` →
人工採集 PNG／metadata → `stereo_calibration` → NPZ／報告 →
`rectification_preview` 依設定與雜湊核對後 remap。

`tools/camera_info.py` 查詢相機資訊；`tools/capture_stereo_calibration.py`
只在人工觸發時寫影像，不會持續錄影或自動大量收集。
`vision/calibration_data.py` 共用資料存取、雜湊及 NPZ 載入。
`vision/stereo_pairing.py` 負責工程配對，不控制同步曝光。

## 棋盤與採集準備

- 使用平整棋盤，量測每格的實際邊長，單位 mm；列印縮放不可直接假設正確。
- `board_cols`、`board_rows` 是內角點數，不是方格數；9×6 只是例子。
- 約 20–30 對可作起點，覆蓋中央、四角、不同角度及預定工作距離。
- 兩眼都必須完整、清楚看到棋盤；移動後先停穩，減少未同步曝光的運動差。
- 保留棋盤方向辨識，避免兩眼角點編號相反；對稱棋盤可能有 180° 歧義，
  必須在後續品質檢視時確認對應。工具不提供人工修角或保證每次角點排序正確。
- 另外採獨立驗證影像，不全部用於擬合。校正時可暫放棋盤，正式無標記
  操作時移除；本階段不建立桌面四角 ROI。

預定視窗採集指令（需桌面）：

```bash
python -m tools.capture_stereo_calibration \
  --mapping data/stereo_mapping.json --output data/calibration/train-001 \
  --width 640 --height 480 --fps 30 --max-pair-delta-ms 10
```

顯示左／右與 `delta_ms`；Space 儲存畫面上的同一有效對，Q／Esc 結束。
影格超過 `--max-save-age-ms`（預設 500ms，工程值）時拒絕存檔。

沒有桌面時加 `--no-window`，每次在終端機按 Enter 才取觸發後收到的新
影格對並存一對，q 或 Ctrl+C 結束；會印出 delta。按 Enter 後仍需保持
棋盤不動直到回報已保存。這個模式不顯示影像，須事先確認取景。

輸出目錄必須是新的，存在即拒絕。例如採集後的結構是：

```text
data/calibration/train-001/
  session.json
  left/000001.png
  right/000001.png
  metadata/000001.json
```

`pair_id` 包含被丟棄的事件，因此不保證連號。兩眼一定共用同一 id。
session 保存左右 mapping、實際配置、sensor modes、properties、controls、
配對門檻與時間域。每對 JSON 保存每眼相機 Id、程式幀號、感測器時間、
曝光時間、主機接收時間、幾何設定及 PNG SHA-256；沒有感測器欄位不以
主機時間代填。影像與 metadata 同源於一個 request，且輸出只接受有效對。

metadata 最後建立作為完整對的紀錄。若磁碟寫入失敗，可能留下不完整
檔案；不自動刪除，離線校正會拒絕不完整配對，請人工檢查並保留失敗資訊。
這是防覆蓋設計，不是整個檔案系統的交易保證。

## 離線校正

只需要 OpenCV／NumPy，不需要相機或 MediaPipe。可在 Windows 離線操作，
但套件與目前 Python 3.14.6 的相容性仍須在恢復驗證時確認。

以下為 Bash 範例；請自行輸入實際棋盤數與量過的方格尺寸，不能直接
拿標稱 60mm 基線當作方格尺寸：

```bash
read -r -p '內角點欄數: ' BOARD_COLS
read -r -p '內角點列數: ' BOARD_ROWS
read -r -p '實測方格邊長 mm: ' SQUARE_SIZE_MM
python -m vision.stereo_calibration \
  --pairs-dir data/calibration/train-001 \
  --board-cols "$BOARD_COLS" --board-rows "$BOARD_ROWS" \
  --square-size-mm "$SQUARE_SIZE_MM" --output data/stereo-calibration.npz
```

預設至少 10 對可用影像只是工程起點，不是準確度保證；可用 `--min-pairs`
明確調整（不得少於 3），實際仍建議採約 20–30 對且有充分姿態變化。

工具先核對左右與 metadata id 完整性、雜湊、尺寸、相機身分、時間域與
配對門檻，再用 `findChessboardCornersSB` 找角點。損壞、尺寸或幾何
設定不一致、找不到完整角點的影像列為拒絕，保留每對原因。
有效資料不足時失敗，輸出失敗報告，不填入假校正矩陣。

object points 使用實測 square_size_mm 建立 mm 座標；先分眼
`calibrateCamera` 得 K1／D1／K2／D2，再 `stereoCalibrate` 使用
`CALIB_FIX_INTRINSIC` 求 R／T，最後 `stereoRectify` 得 R1／R2／P1／P2／Q
及有效 ROI。這是 OpenCV 的校正 API 路徑，資料格式、配對門檻及拒絕策略
是本專案設計。[OpenCV 官方校正文件](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html)

輸出 `data/stereo-calibration.npz`（`allow_pickle=False` 可讀）包含：

- K1／D1／K2／D2／R／T／R1／R2／P1／P2／Q，可用來重建 remap maps。
- JSON metadata：calibration_id、UTC 建立時間、影像尺寸、左右 Id／順序、
  sensor mode／crop／transform、棋盤內角點與實測格長、有效 ROI。
- 單眼與雙目 RMS、每對單眼重投影 RMS 與校直後角點垂直殘差、可用及拒絕
  清單、PNG 雜湊、採集設定與 OpenCV 實際版本。
- 計算所得 `baseline_mm=norm(T)`、產品標稱 60mm 與比值；只作合理性比較，
  不把結果強制改成 60。產品 2.6mm 焦距也不是 K 裡的像素焦距。

另輸出 `.npz.report.json`；既有校正檔或報告都不覆蓋。
擬合成功只會標為 `fitted_only_not_independently_validated`；
RMS 小也不能排除錯誤尺度、角點歧義、姿態不足或未同步運動造成的問題。
本草稿沒有自動剔除高殘差資料後反覆擬合，也沒有自動品質合格門檻。

## 用獨立資料看校直前後

另外以同樣尺寸及相機幾何設定採 `data/calibration/validation-001`，
不把這組影像放入上述擬合目錄。從實際存在的 pair_id 選一對：

```bash
python -m vision.rectification_preview \
  --calibration data/stereo-calibration.npz \
  --left data/calibration/validation-001/left/000001.png \
  --right data/calibration/validation-001/right/000001.png \
  --pair-metadata data/calibration/validation-001/metadata/000001.json
```

上排原圖、下排校直圖，疊水平線並標出 calibration_id 與輸入尺寸。
看同一實體特徵是否落在同一高度；這是人工檢視輔助，畫線本身不代表校正
正確。Q／Esc 關閉。缺檔、左右相反（雜湊／Id 不符）、輸入尺寸或幾何
設定不符時拒絕使用，不自動換眼或縮放。

純文字環境可加 `--no-window --output data/rectification-review.png`，
由使用者明確指定才產生 PNG，既有檔不覆蓋。離線影像必須有採集工具的
metadata；任意來源或被編輯過的圖片不當作已確認的同一幾何配置。

## 重校正與下一步

對焦、裁切、sensor mode、影像尺寸、翻轉、相機相對位置或安裝結構改變
後，不能盲用舊校正檔。實際棋盤尺寸、左右確認、擷取模式與真實量測仍
須由人取得；tuning JSON 不是幾何校正結果。

未來若手部追蹤改用校直左圖，深度也必須使用同一校直座標系。不得拿
原圖 Landmark XY 直接索引校直深度，也不單獨對某眼做未記錄的鏡像／裁切。
本次不做 StereoSGBM、桌面平面、四角 ROI 或觸碰判斷；未證明雙目深度或
桌面接觸可行。恢復驗證後先檢查擷取／中斷清理、配對拒絕、PNG 完整性、
校正報告及獨立校直影像，再決定後續工作，並請另一位組員審查。
