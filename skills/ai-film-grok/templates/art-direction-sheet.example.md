# Art Direction Sheet — 美术设计表模板

> P1-6 美术设计 art direction · 脱离单字符串 palette/lighting
> 色温脚本/视觉母题/质感锁定——成片"电影感"的核心。

## 色温脚本 (color_script)

| scene_id | color_temperature | palette_override | emotional_motivation |
|---|---|---|---|
| sc01 | cool 5600K + warm 3200K 混合 | 深蓝/霓虹粉 | 孤独·城市疏离 |
| sc02 | warm 3200K | 暖黄/橙 | 信任·室内温暖 |
| sc03 | neutral 4500K | 灰白/冷青 | 真相·冷静客观 |
| sc04 | warm 2800K + golden hour | 金色/暖棕 | 释然·新常态 |

### 色温弧线

色温随叙事推进变化：冷(孤独) → 暖(信任) → 中性(真相) → 金色(释然)。
这是"色彩叙事"——不靠台词，靠色温讲故事。

## 视觉母题 (visual_motifs)

| motif | first_appearance | recurrence_rule |
|---|---|---|
| 雨=疏离 | sc01 | 每当角色拒绝连接时出现雨 |
| 伞=保护 | sc01 | 从递伞到共撑，伞的大小变化映射关系 |
| 红门=危险 | sc02 | 真相揭露场景出现红色门框 |
| 阳光=接受 | sc04 | 最终接受时雨停、阳光出现 |

## 质感锁定 (texture_continuity)

| element | lock_description |
|---|---|
| 皮肤质感 | 半哑光，不油腻，保留毛孔细节 |
| 湿地面 | 始终有镜面反射，水纹方向一致 |
| 伞面材质 | 尼龙半透明，雨滴可见 |
| 墙面纹理 | 粗糙水泥，霓虹反射斑驳 |
| 衣物质感 | 风衣表面微湿，褶皱一致 |

## 与 grade 参数的关系

`film-spec.grade` 控制全局调色参数（LUT/saturation/contrast/skin_tone_protection）。
`art_direction.color_script` 控制场景级色温脚本——是"设计意图"层。
两者配合：art_direction 定义"应该是什么色"，grade 定义"怎么把像素调到那个色"。
