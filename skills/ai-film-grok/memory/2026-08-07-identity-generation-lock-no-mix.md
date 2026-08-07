# Memory · 2026-08-07 · 身份代际锁 · 禁混代出片（P0 · abroad 漂移事故）

> **类比**：同集不能一半「旧发型剧照」一半「新定妆剧照」剪在一起当同一人。  
> **片例**：`AI FILM SPACE/0806/abroad-slut-manhua-h3`

## 用户原话
> 漂移太严重了 前后对不上 请你自己反思 如何不要再犯错误 回写教训

## 事故（agent 自责）
1. **`face-identity.verified=false` 仍 bulk→final**，把「有 clips」当「角色一致」。  
2. **半套 cast restyle（leon）**：`takes/_archive_pre_leon_restyle` 与 restyle 后 takes **混进同一 `film_final`**；后又从 archive **静默 restore** 缺镜。  
3. **未做人/机读身份门**就交付可看版；ahash 漂（worst ~40+/64 vs master）仍报 PARTIAL 出片。  
4. **final 优先修声不修脸**——用户观感是「前后不是同一人」，声轨再干净也白费。

## 三句话
1. **一代一脸一集**：同一 film root 的 active timeline **只能有一个 cast generation**（`cast_generation_id` / restyle batch）；混代 = 必漂。  
2. **`verified≠true` 禁声称角色稳定**；final 可技术出 plate，但必须 **IDENTITY_PARTIAL**，禁暗示「对得上」。  
3. **restyle / 换男主锚 / 换定妆** → **整集重锚 still→H3 全轨**，或 **新 film root**；禁止 archive 抽几镜填洞。

## 检查清单（final / ship 前）
- [ ] `receipts/face-identity.json` → 主角色 **enrolled + verified=true**（或显式 `IDENTITY_PARTIAL` 收据）  
- [ ] active clips **无** 跨 `generation` / `_archive_*` 混用；restore 须标代并拒 silent  
- [ ] still/keyframe 均绑 **当前** cast master / face-lock（禁旧 gen keyframe 进 H3）  
- [ ] pilot 三镜用户批脸后才 bulk；改 cast 后 **作废** 旧 pilot 与旧 takes  
- [ ] final 前跑 identity drift 审计；worst 镜 **先 re-I2V** 再拼片  
- [ ] 有 plate ≠ 脸对；**有声干净 ≠ 角色对**

## 链
- hard-defaults 表行「身份代际锁」  
- **机读 E1：** `gates/identity_generation_lock.py` · closeout `identity_generation` · `receipts/cast-generation.json`  
- face-identity CLI · cast masters · firstframe-fill memory  
- escape：`AIFILM_SKIP_IDENTITY_GEN=1`  
- 本片 drift：`receipts/identity-drift-ahash.json` · `takes/_archive_pre_leon_restyle/`
