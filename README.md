<<<<<<< HEAD
# 網頁控制台｜B

目前未實作。先做三個固定區域、游標、hover／pressed／lost 狀態，以及連線與設備狀態。按鈕區域讀取 shared/buttons.json，避免與 IoT 各自寫一套座標。

先用模擬事件開發，再接真實事件。瀏覽器傳輸方式須明確選擇 Node-RED 橋接或 MQTT over WebSocket；不要直接連 MQTT TCP。

網頁顯示「觸控已偵測」與「設備已回報執行」兩種狀態，不能只收到 touch_down 就顯示硬體操作成功。失去連線或 tracking_lost 時清除按壓外觀。
=======
# MagicBlank
Touch the Invisible.
>>>>>>> origin/main
