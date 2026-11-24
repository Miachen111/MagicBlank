# IoT 與 Node-RED｜B

目前未實作。先用模擬事件或滑鼠輸入完成 LED 路徑，再整合真實觸控。

接收觸控、去重與有效性檢查 → 根據 shared/buttons.json 映射 → 發送設備命令 → 實際執行端回報狀態。只有 touch_down 觸發；不因 hover、重複封包、無效追蹤或重播事件重複操作。

Node-RED 流程匯出為 flows.json 再納入 Git，排除 flows_cred.json、密碼與私人設定。整合前先備份現有流程。Pi 型號、系統與 Servo 規格未定，不預填 GPIO 或控制套件。

LED 可先實作明確的 on／off 指令，降低重送造成 toggle 反轉的問題。Servo 動作範圍、電源及位置／連續旋轉型須確認後才能實作。
