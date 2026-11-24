# GhostTouch 事件協定 v1

本檔是跨模組介面依據。修改前先同步兩人，版本不相容時提升 schema_version。

## 觸控事件

MQTT 建議 topic：`ghosttouch/v1/<device_id>/touch`。不保留事件（retain=false），不得把舊觸控重播成新指令。QoS 1 可能重送；實際 MQTT 程式需自行設定並驗證，本框架尚未實作傳輸。

| 欄位 | 型別／範圍 | 定義 |
| --- | --- | --- |
| schema_version | 整數 1 | 協定版本 |
| device_id | 非空字串 | 互動桌面識別 |
| session_id | 非空字串 | 每次視覺程式啟動產生新 UUID |
| seq | 正整數 | 同一 session 嚴格遞增 |
| timestamp_ms | 非負整數 | Unix epoch 毫秒，供紀錄；不保證跨機器時鐘同步 |
| source | vision／simulated | 真實視覺或模擬資料 |
| mode | surface_touch／pinch | 表面觸控或捏合備案 |
| event | hover／touch_down／touch_up／tracking_lost | 事件種類 |
| x、y | 0～1 或 null | 桌面正規化座標；tracking_lost 時兩者為 null |
| distance_mm | 非負有限數或 null | 估計指尖距平面高度；無效或未知為 null |
| confidence | 0～1 或 null | 自定義品質分數，非準確率；未定義前使用 null |

非 tracking_lost 事件必須有有效 x、y。surface_touch 的 touch_down 必須有有效 distance_mm；不可拿未知深度產生表面觸控。捏合可使用 null。追蹤遺失的 distance_mm 與 confidence 皆為 null。

座標原點：使用者面向桌面時的左上角；x 向右、y 向靠近使用者方向增加。相機影像是否鏡像不改變此約定。區域外不夾到邊界產生點擊；先在視覺層拒絕。桌面範圍與座標基底由校正資料決定。

## 狀態與重送
- 尚未按壓：hover 可更新游標；符合條件才送一次 touch_down。
- 已按壓：可繼續 hover 更新位置，但不再次送 touch_down；離開接觸條件送一次 touch_up。
- tracking_lost：取消按壓且不執行設備動作；恢復後先重新建立 hover／釋放狀態，不直接按下。
- 接收端按 device_id、session_id、seq 去重。新 session、重連與來源切換要清除舊按壓狀態；正式接收端還須有 session 握手或其他過期事件拒絕機制。
- 單靠 seq 或 timestamp 不足以阻止所有舊連線重播；完成傳輸時必須明確設計並驗證。只有即時且通過驗證的 touch_down 可執行動作。

## 按鈕設定

buttons.json 使用固定矩形區域。命中條件為 `x_min <= x < x_max`、`y_min <= y < y_max`，避免相鄰邊界重複命中。按鈕不可重疊；邊界 1.0 不包含於任何按鈕。三個動作暫定 LED 開、LED 關、Servo 預設位置，Servo 尚未啟用。

## 後續設備介面

建議命令 topic：`ghosttouch/v1/<device_id>/command`，執行回報：`ghosttouch/v1/<device_id>/state`。命令需 command_id，回報需對應 command_id、結果與實際狀態。命令與回報格式尚待 B 實作前共同確定，尚不屬於可用介面。

不使用 retained 動作命令。避免把模擬來源送到真實設備；硬體端預設拒絕 simulated，只有明確開啟測試模式時接受。伺服動作另受已確認的角度／速度與供電限制。
