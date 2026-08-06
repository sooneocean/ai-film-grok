# Character Bible — 角色设定表模板

> 40 年导演方法论注入 · P0-3 角色设定表
>
> 每个角色一张完整设定表。protagonist 必须有 want/need/arc（character_bible_strict: true 时 write-spec 硬校验）。

---

## 角色：{name}

| 字段 | 值 | 说明 |
|---|---|---|
| **id** | `hero` | 唯一标识，用于 schema 引用 |
| **name** | 苏念 | 角色姓名（戏剧身份，非视觉描述） |
| **age** | 28 | 年龄或年龄带（如 "mid-20s"） |
| **dramatic_role** | `protagonist` | 戏剧功能：protagonist/antagonist/mentor/ally/trickster/guardian/supporting |

### 视觉身份 (identity)

物理描述：脸/眼/发/体型/肤色等——用于 cast master 生成与锁脸。

```
清冷面孔，丹凤眼，银白及腰长发，白皙肤色，纤瘦身材，约168cm。
```

### 性格 (personality)

3-5 个核心特质词。

```
克制、聪慧、外冷内热、执念深、不信任他人
```

### 戏剧弧线 (dramatic arc)

| 字段 | 值 | 导演笔记 |
|---|---|---|
| **want**（想要） | 查清父亲死因的真相 | 外在目标——驱动行动 |
| **need**（需要） | 学会信任他人、接受脆弱 | 内在成长——角色真正需要的 |
| **flaw**（缺陷） | 不信任任何人，凡事独自承担 | 阻止成长直到弧光解决 |
| **ghost_wound**（创伤） | 父亲在她面前死去，她未能救他 | 驱动行为的过去伤疤 |
| **arc**（弧光） | 孤狼复仇者 → 愿意依赖他人的伙伴 | A→B 状态转变 |

### 转折点 (arc_turning_points)

关键转变时刻，映射到 beat id。

1. `hook` — 发现父亲遗物中的线索，决定独自追查
2. `approach` — 遇到搭档，拒绝合作
3. `rising` — 独自调查失败，险些丧命
4. `turn` — 接受搭档帮助，第一次信任他人
5. `climax` — 面对真凶，放下执念选择正义而非私刑
6. `resolution` — 与搭档并肩，接受新的关系

### 关系网 (relationships)

| 对谁 | 类型 | 动力 |
|---|---|---|
| `partner` (陆深) | ally → lover | 从不信任到依赖；权力对等但情感不对等 |
| `villain` (赵衡) | antagonist | 父亲旧友，真相揭露者；表面的善意下是利用 |
| `mentor` (老周) | mentor → guardian | 教父式人物，保护但隐瞒真相 |

### 心理外化标记 (psych_markers)

身体语言/习惯/微表情——给演员（或 I2V）的表演颗粒度。

- 紧张时右手无意识摸左腕疤痕
- 说谎时目光向右下偏移
- 信任时肩膀放松，呼吸变深
- 愤怒时沉默而非爆发

### 服装 (defaultWardrobe + wardrobe_variants)

| 场景 | 服装 | 状态 |
|---|---|---|
| 日常 | 黑色风衣、白衬衫、深灰长裤 | full |
| 调查 | 同上，加手套 | full |
| 受伤 | 白衬衫染血，风衣破损 | partial |
| 结局 | 浅色外套，脱去黑色——象征放下执念 | full |

### cast master

```
cast_state_masters:
  hero:
    full: assets/cast/hero_full.png
    partial: assets/cast/hero_partial.png
```

---

## 角色：{name2}

（重复以上结构，为每个重要角色填写。antagonist 至少需要 want + flaw。）
