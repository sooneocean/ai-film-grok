# Production State Map（愿景闸 ↔ 现系统）

> **P0 · Film Production OS** · 投影表，**不改**用户可见 7 段进度名。  
> 单一执行板：[film-production-os-todoplan](../../../docs/plans/2026-08-07-film-production-os-todoplan.md)

## 用户主进度（唯一对外）

```text
定义故事 → 设计演出 → Pilot 样片 → 批量制作 → 选片与粗剪 → 后期母版 → 审片与交付
```

内部兼容：`agent → visual → voice → post → deliver` · craft 八环 · Professional 11 阶段。

## 愿景审批闸 → 现仓

| 愿景状态 | Professional 11 | dispatch 7 段 | 机读/命令（现有或 OS 波次） |
|----------|-----------------|---------------|---------------------------|
| IDEA | — | 定义故事 | intake / story.receive |
| CONCEPT_APPROVED | concept_lock | 定义故事 | `director lock-stage --stage concept_lock` |
| STORY_DEVELOPMENT | — | 定义故事 | plan run · debrief |
| STORY_APPROVED | — | 定义故事 | `story validate-structure` · story_quality |
| SCRIPT_DRAFT | — | 定义故事 | drama-graph draft |
| SCRIPT_LOCK | script_lock | 定义故事 | `director lock-stage --stage script_lock` |
| BREAKDOWN_COMPLETE | — | 设计演出 | beat extract · scene cards |
| ASSET_DEVELOPMENT | department_look_lock 前 | 设计演出 | cast / style / wardrobe |
| ASSET_LOCK | department_look_lock | 设计演出 | department lock |
| STORYBOARD | shot_animatic_lock 前 | 设计演出 | still 草稿 · shot cards |
| ANIMATIC | shot_animatic_lock | 设计演出 / Pilot | animatic gate · lock-stage |
| ANIMATIC_APPROVED | shot_animatic_lock | Pilot | native stage evidence |
| SHOT_LOCK / SHOT_READY | — | Pilot 后 | generation_ready · bulk-preflight |
| GENERATING | bulk | 批量制作 | media-queue · h3 run-next |
| SHOT_REVIEW | dailies_review | 选片与粗剪 | register · review |
| SHOT_APPROVED | selects_rough_cut | 选片与粗剪 | take select · selects |
| ASSEMBLY / ROUGH / FINE | selects_rough_cut | 选片与粗剪 | editor_cut · plate |
| PICTURE_LOCK | picture_lock | 后期母版 | picture_lock |
| VFX_FINAL / SOUND_FINAL | post_locks | 后期母版 | post-bible locks |
| MASTER_QC | master_lock | 审片与交付 | gate-auto · closeout |
| DELIVERED | master_lock | 审片与交付 | export · review-final |

## 生产图实体（现仓）

| 愿景 | 现仓 | 备注 |
|------|------|------|
| CreativeIntent | `director_intent` + creative fields | `creative_intent_strict` |
| Sequence | longform / episode 内扁平 | 短片可省略 |
| Scene / Beat / Shot | drama-graph · film-spec | 真相 graph，spec 投影 |
| Shot Card | `aifilm shot-card` | OS W2 |
| Take | take_registry | 不覆盖 |
| Prompt | 执行物 | 禁回写 provider 语法进 graph |

## 反模式（冻结）

1. **禁**新建第二套 `DirectorAgent` 绿地包（用 director_cli + receipt + gate）。  
2. **禁**剧本/screenplay 直灌视频模型（须 Scene→Beat→Shot）。  
3. **禁**无 `shot_purpose` / 仅「好看 cinematic」的 shot 进 bulk。  
4. **禁**Generation 反向改 Story 而不走 impact/stale。  
5. **禁**只写 memory 当立法（须 schema + pytest + hard-defaults）。

## 相关

- [professional-director-system.md](professional-director-system.md)  
- [pipeline-methodology.md](pipeline-methodology.md)  
- [generative-film-craft.md](generative-film-craft.md)  
- [stages/approval.md](stages/approval.md)  
