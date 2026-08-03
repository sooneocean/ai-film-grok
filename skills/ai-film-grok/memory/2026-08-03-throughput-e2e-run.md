# Memory · 2026-08-03 · 吞吐主链 e2e 跑通

**plugin 线：** Wave A–H 已在 origin 历史（至 v2.31.26+）；本卡只记 **实跑**。

## 用户原话
> 帮我跑通 · 弄一弄准备收工

## 三句话
1. **冒烟根** `/tmp/aifilm-e2e-c2Q0QU`：variety → pilot GO → bulk 绿 → shortlist → tunnel/lease/progress → closeout 停 review-final → dispatch/audio-plan → media-queue add **OK**。  
2. **Wave H 复用**：`assert_bulk_preflight` 绿收据 `reused=true`（film-spec 未更新时）。  
3. **IRON 未破**：closeout 不自批 final；advance 拒 `scene-sound-plan`；bulk 前须 scorecard+用户「pilot 过」。

## 检查清单
- [x] variety-precheck ok  
- [x] pilot-pack ok（合规 scorecard + pilot-approval）  
- [x] bulk-preflight failed=[]  
- [x] select-shortlist 优选更大 take  
- [x] tunnel :18188 / gpu-lease free / takes_files=6  
- [x] media-queue add 过 pilot-go + bulk 门  
- [x] closeout → review-final 人审门  
- [ ] 真片 film root 同一路径（用户点名）  
- [ ] W8 autopilot allowlist（未开）

## 注意（冒烟坑）
- soft fixture 须：**独立 still 字节**、**keyframe 704×1280 9:16**、state generate_plan 空，否则 bulk 挂 geometry/still_uniqueness/state_index。  
- `pilot score` CLI 可被 cinematic audit 拦；真片先补创意合同/镜头动势，或人审后写合规 scorecard 再 approve。  
- aifilm `ok=false` 常 **exit 2**；脚本链勿裸 `set -e` 无 `|| true`。

## 关联
- [2026-08-03-workflow-merge-all-wrap.md](./2026-08-03-workflow-merge-all-wrap.md)  
- hard-defaults · stages/post · closeout IRON
