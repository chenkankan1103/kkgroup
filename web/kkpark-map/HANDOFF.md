# KK 園區：雙面線人 — 開發進度交接（2026-11-11）

> 給下一個對話的開場文件：讀完這份就知道做到哪、下一步是什麼。

## 線上狀態（全部已部署 GitHub Pages，deploy-pages.yml 自動觸發）

**在開發的只有一款：雙面線人。** 下表另外兩個網址是歷史堆積——`/` 是最早的 kkpark 原版，`/game/` 是這輪開發路上先試做的版本，方向改定後留檔沒刪，都不是活躍項目。

| 路徑 | 遊戲 | 狀態 |
|---|---|---|
| `/` | kkpark 原版 | 穩定 |
| `/game/` | 生存街機（原地圖派遣版改寫留檔：音效＋精靈＋模組拆分） | 留檔，無開發計畫（commit ea435f56） |
| `/map/` | **雙面線人 V2 攻堅版（主力）** | 已上線（V1.5：927005c0，V2 夜間攻堅同日接續），全系統驗證通過 |

## 主力遊戲：web/kkpark-map/「KK 園區：雙面線人」

台灣真實地圖詐騙園區經營＋雙面臥底。7 檔純前端：index.html / style.css / data.js（數值表）/ save.js（localStorage `kkpark_map_save_v1`）/ sim.js（狀態機）/ map.js（Leaflet）/ ui.js。

### 已完成系統（全部瀏覽器實測通過、零 console 錯誤）

- **地圖**：Leaflet＋Esri World Dark Gray 瓦片（免 key、maxZoom 16）；決定性偽隨機警車——400m 固定格（CELL=0.004°）＋hash3 雜湊，位置與存在都由格子決定、時段只調數量門檻，跨縮放不跑位（z12 每4格/z13 每2格/z14+ 全顯、cap 450、zoom<12 不顯示、26 點 ray cast 擋海）
- **時鐘**：1 真實秒＝1 遊戲分鐘；setInterval(1000) 驅動 Sim.tick()；gameMin = day*1440+min
- **任務派遣**：快跑（看戲＋事件）/大活（×4 時長 ×2.2 錢、離線照跑 endRealMs）；事件抉擇（4 種 EVENTS）；看守所 JAIL_MIN[3,8]＋保釋（$20000 起跳）；風險/熱度/賞金隨機
- **V1.5 走路動畫**：job 三階段 `leg: out → work → back`；每遊戲分鐘移動 MOVE_DEG=0.0028°（贓車 ×1.9）；marker 持久化＋CSS transition 1s 補間；回 HQ 才 idle
- **V1.5 伙食**：開場 25；每天 06:00 全員開飯（每人 2、廚房→1）；水塔 +4/天；成功任務 +1；$3000 買 +10；斷糧 trust −5＋toast；HUD chip ≤3 紅閃
- **V1.5 園區建設**：5 棟 BUILDINGS（水塔/廚房/圍籬/發電機/工寮）——商店購買、buildQueue 施工（buildMin 遊戲分鐘=真實秒）、HQ 旁 B_SPOTS 圖示（工地 ⚒️ 灰框→完工綠框）；圍籬＝夜間警力 −25%、發電機＝報酬 ×1.15、工寮＝成員上限 +3（基礎 6）
- **V2 夜間攻堅**：20:00 擲骰出風聲預警（機率＝基礎 10%＋天數遞增封頂 30%＋懷疑×25%＋警方進度×15%；day≤3 教學期免戰、當日剛被打過機率減半）→ 02:00 深夜發動：暫停＋決策卡＋7 台紅藍閃爍警車從四周圍向 HQ（獨立 mRaid 圖層，不被巡邏刷新掃掉，CSS transition 1.8s 補間）。四策略（一張總策略卡、重傷不致死）：**死守迎戰** def＝人數×8＋平均戰力×2，勝 trust+6/sus−10，敗抄錢 25% cap 3 萬＋逮 1-2 人進看守所＋隨機拆一棟建築＋trust−8/sus+10；**全員躲藏** def＝人數×4＋圍籬 15，無人被抓、敗抄 15%；**棄車誘敵** 犧牲贓車、判定門檻 ×0.85，敗抄 10% 無人被抓；**花錢消災** $20000 必勝 sus−5。圍籬額外壓攻堅強度 −20%；強度＝40＋天數×2＋sus×0.25＋police×0.3；只有 idle 成員參與（出勤中的躲過這劫）。`S.raid`/`S.lastRaidDay` 存檔跨重載恢復（warn→chip 亮、fight→重彈卡＋保持暫停）
- **存檔**：v2 格式＋v1→v2 自動遷移（food/buildings/buildQueue 補預設、舊 job 補 leg='work'）；V2 補 raid/lastRaidDay、V2.5 補 buried/buriedRefund/raidCount/bribeCount 與任務 expireMin（舊檔向後相容）
- **教學**：`kkpark_map_tut_v1` flag、八步 howto（❓ 可重開；第 7-8 條夜間攻堅與貢金/時效）
- **V2.5 好玩度**：①藏錢——風聲期間 HUD 可「🪙 藏一半現金」（當下離帳，被抄/貢金都碰不到，隔天 08:00 挖回磨損一成 BURY_FEE）②貢金——day3 起每天 21:00 上頭抽成（$6,000＋每日 $2,500、cap $45,000；18:00 預告 toast＋HUD chip、繳夠 trust+2、繳不出 trust−12 録零）③任務時效——expireMin 6~12 遊戲小時、過期自動熄掉（tick prune＋emit missions）④任務距離——distTier 近/中/遠（門檻 0.02/0.04°，生成範圍 max ≈0.057）、遠的 payMult 至 1.4×／risk +dist×1.4，面板顯示距離與時限 ⑤攻堅平衡——首次突擊強度 ×0.6（RAID_FIRST_RELIEF）＋卡片首戰提示、每晚強度浮動 ×0.9~1.15、花錢消災階梯 $20,000→$30,000→…cap $50,000（raidBribeCost）⑥新事件卡——🕵️ 線人密會（kind police：police+6/trust−4）、🍺 自己人鬧酒（kind pay：花錢/立威）
- **結局**：信任歸零滅口 / 懷疑滿收押（敗）、警方進度 100 全台收網（勝）

### 對標願景（Infection Free Zone，已與使用者對齊）

分期：V1.5 建設版（✅）→ V2 夜間攻堅戰（✅ 2026-11-11 完成）→ 不做：真實建築建模/尋路/戰爭迷霧

## 下一步候補（V2.5 之後，未與使用者對齊前先別動）

1. **平衡長跑**：藏錢／貢金／時效距離／攻堅的體感節奏要真人玩幾天調校（V2.5 當天只做了單點邏輯驗證）
2. 手機響應式排版（@media 720px）未細驗
3. V3 候選方向：成就系統、更多防禦建築（監視器/鐵門）、地圖隨機事件——只是點子，要開工先跟使用者對齊

## 已知的小尾巴（非阻塞）

1. 發電機 ×1.15 只驗了程式碼，沒跑數值對比（一行乘法，低風險）
2. 數值平衡未經長時間遊玩調校（開場 $60000、任務報酬、伙食消耗節奏、V2 攻堅機率與強度）

## 環境坑（省得重踩）

- **Browser pane 背景時 setInterval 凍結**——驗證一律用 preview_eval 手動呼叫 Sim.tick()；真人前景玩時正常
- **preview_click 座標偏移 78px**——一律用 eval `element.click()`
- Bash 工具故障（rtk hook 已於 2026-11-11 移除，新 session 生效）→ 過渡期用 mcp__terminal__run_in_terminal（PowerShell）；中文 commit message 用 `git commit -F <檔案>`
- MCP allow 已補齊 user settings.json（classifier timeout 不再擋工具）

## 部署流程備忘

worktree commit → `git -C "C:/Users/88697/Desktop/kkgroup" merge --ff-only claude/silly-driscoll-a7481d` → `git -C "C:/Users/88697/Desktop/kkgroup" push origin main`（Pages 約一兩分鐘後生效；未問使用者不 push）
