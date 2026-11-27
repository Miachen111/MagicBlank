# MagicBlank

Touch the Invisible.

MagicBlank 是兩人、三週的課程原型，目標是以相機追蹤手指，將桌面上的固定區域作為虛擬按鈕，再由 IoT 層映射為設備操作。專案內的 GhostTouch 名稱用於既有協定與 MQTT topic。

目前已有視覺測試程式、雙目工具草稿、共用事件協定與離線模擬工具；桌面接觸辨識、網頁控制台與設備整合仍待完成。**未做硬體實測，尚不是可直接部署的完整系統。**

## 專案目錄與文件

| 路徑                                    | 用途                                                                     |
| --------------------------------------- | ------------------------------------------------------------------------ |
| [vision/](vision/README.md)              | A：影像來源、手部追蹤、雙目配對與校正工具                                |
| [dashboard/](dashboard/README.md)        | B：控制台規劃與顯示狀態要求                                              |
| [iot/](iot/README.md)                    | B：事件接收、按鈕映射、Node-RED 與設備回報規劃                           |
| [shared/PROTOCOL.md](shared/PROTOCOL.md) | 跨模組事件格式、座標、追蹤遺失與重送規則                                 |
| `tools/`                              | 離線協定檢查、事件模擬與相機／校正輔助程式                               |
| `test_webcam.py`、`test_pinch.py`   | Windows 單相機食指與捏合測試入口                                         |
| [docs/PLAN.md](docs/PLAN.md)             | 三週計畫、決策點與完成條件                                               |
| [docs/DECISIONS.md](docs/DECISIONS.md)   | 技術決策紀錄；D001 保留早期筆電視覺預設，Pi 路徑的後續資訊見視覺模組文件 |
| [docs/TESTING.md](docs/TESTING.md)       | 硬體測試與量測紀錄模板                                                   |
| `data/`、`models/`                  | 本機影像、校正資料與模型；不提交 Git                                     |

## 第一次使用：先選擇工作

| 想做的事情                    | 準備與入口                                                                                              |
| ----------------------------- | ------------------------------------------------------------------------------------------------------- |
| 改文件、了解事件格式          | 不需第三方套件；閱讀 [事件協定](shared/PROTOCOL.md)                                                      |
| 不接相機，先看模擬輸出        | 準備 Python 後，執行下方「離線檢查與模擬」                                                              |
| 用 Windows 相機看食指或測捏合 | 建立虛擬環境 → 安裝 `requirements-vision.txt` → 準備模型 → 執行測試程式                            |
| 在 Windows 做離線雙目校正     | 使用獨立環境與 `requirements-calibration.txt`，依 [校正指南](docs/STEREO_CALIBRATION.md) 操作          |
| 在 Pi 擷取雙目影像            | 先讀 [相機設定](docs/CAMERA_SETUP.md) 與 [依賴分流](vision/DEPENDENCIES.md)，確認系統、接線與左右相機身分 |

以下 PowerShell 指令皆從專案根目錄執行。若要修改檔案，先依下一節建立分支；只執行現有工具可直接準備環境。

## 開發前：建立工作分支

先確認目前分支與修改。若有未提交工作，先確認歸屬並保存，再切換分支或更新 `main`。

```powershell
git status
git branch --show-current
```

工作目錄乾淨時，從更新後的 `main` 建立分支。以下以整理 README 為例：

```powershell
git switch main
git pull --ff-only origin main
git switch -c docs/development-setup
```

若已在正確起點，只需 `git switch -c docs/development-setup`；目前未提交的修改會留在新分支的工作目錄。分支已存在時，用 `git switch docs/development-setup` 切回。`--ff-only` 若失敗，先確認本機與遠端差異，不強制覆蓋或重設歷史。

## 環境準備（Windows／PowerShell）

### 1. 建立與啟用虛擬環境

先確認已安裝 Python；若要使用視覺工具，還需確認其版本有相容的套件。首次建立環境時執行：

```powershell
python --version
python -m venv .venv
```

每次開新終端機時啟用既有環境，並確認使用的 Python 路徑：

```powershell
.\.venv\Scripts\Activate.ps1
python -c "import sys; print(sys.executable)"
```

輸出應位於專案 `.venv`。VS Code 使用 `Python: Select Interpreter` 選取同一環境。若 PowerShell 阻擋啟用腳本，可直接以 `.\.venv\Scripts\python.exe` 取代下方指令中的 `python`，不必更改系統執行原則。

**開 Git 分支不需要重建虛擬環境。** 同一份工作目錄的分支共用本機 `.venv`；切換分支後，依賴有變時才更新環境。結束開發時，可用 `deactivate` 離開已啟用的環境。

### 2. 安裝本次工作需要的套件

只改文件或執行離線事件工具可跳過此步。Windows 食指追蹤與捏合測試使用：

```powershell
python -m pip install -r requirements-vision.txt
```

若本次只做離線雙目校正，改在另一個獨立環境使用：

```powershell
python -m pip install -r requirements-calibration.txt
```

兩份清單選用不同的 OpenCV 發行包，**不要在同一環境混裝**。它們目前都是未鎖版的候選清單，不是已驗證的可重現安裝環境；安裝後需記錄實際 Python、平台與套件版本。

Pi 使用另一套系統準備流程：Picamera2／libcamera 由相容的系統環境提供；使用系統 OpenCV 時，不直接套用上述 pip 清單。完整方式見 [依賴分流](vision/DEPENDENCIES.md)。

### 3. 準備手部追蹤模型

只有食指追蹤與捏合測試需要 `hand_landmarker.task`；離線事件模擬與雙目校正不需要。模型取得方式見 [視覺模組說明](vision/README.md)。

執行根目錄測試時，將模型放在 `test_webcam.py`、`test_pinch.py` 旁。`test_webcam.py` 也支援 `--model` 指定其他路徑；模型不隨程式自動下載，也不提交 Git。

## 執行與檢查

### 離線檢查與模擬（不開相機）

```powershell
python tools/check_contract.py
python tools/simulate_touch.py
```

第一個指令檢查共用事件範例與按鈕區域，通過時印出 `PASS`。第二個指令輸出四筆 JSON 事件，依序是 `hover`、`touch_down`、`touch_up`、`tracking_lost`，且 `source` 為 `simulated`。這些工具不連接 MQTT 或操作 GPIO。

### Windows 食指追蹤與捏合

安裝視覺依賴並放好模型後，先檢查套件、模型及兩幀人工空白影像推論：

```powershell
python test_webcam.py --check
```

這項檢查不開攝影機。要觀察真實畫面時，以下兩個程式擇一執行，結束後再切換：

```powershell
# 顯示食指尖；視窗按 q、Q 或 Esc 結束。
python test_webcam.py

# 測試捏合；視窗按小寫 q 結束。
python test_pinch.py
```

食指測試只有 2D 影像座標；捏合測試只將事件印到終端機，沒有輸出完整的 shared 協定封包或控制設備。捏合開始及追蹤恢復後，須先張開再捏合。相機權限、編號與人工驗證步驟見 [Windows 測試指南](docs/WEBCAM_TEST.md)。

### Pi 雙目擷取與校正

依 [相機設定](docs/CAMERA_SETUP.md) → [雙目校正指南](docs/STEREO_CALIBRATION.md) → [視覺模組說明](vision/README.md) 的順序準備。現有工具只做雙路接入、時間配對與校正，不代表曝光同步、毫米深度或桌面接觸已驗證。

## 完成修改：驗證與提交

開始修改前閱讀 [AGENTS.md](AGENTS.md)、相關模組 README、[事件協定](shared/PROTOCOL.md) 與 [技術決策](docs/DECISIONS.md)。修改 `shared` 或 `tools` 時，必須執行上方協定檢查與事件模擬；其他關鍵邏輯依實際變更驗證。

以下以只修改 README 為例；其他任務只加入本次變更的檔案，檢查暫存差異後才提交：

```powershell
git diff --check
git add README.md
git diff --cached
git commit -m "docs: 整理 README 與開發環境準備步驟"
```

要分享此分支時，再執行：

```powershell
git push -u origin docs/development-setup
```

推送後開 PR，說明改動、驗證結果與限制，交由另一位組員審查，AI 產出的修改也適用。不直接合併或推送 `main`；不提交虛擬環境、模型、影像、密碼或憑證。

目前下一步是完成真實相機追蹤與校正驗證，再評估桌面深度／接觸可行性，並以模擬事件開發控制台及 LED 路徑。模擬成功不代表真實觸控、MQTT 整合或設備操作成功。
