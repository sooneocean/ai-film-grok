# Lessons · 角色立场剪辑

> 2026-07-20 · 用户：剪辑同时考量不同角色立场，提高画面层次  
> 权威：[character-stance.md](character-stance.md)

## 一句话

**focal + viewpoint + look_axis** 是剪辑与构图的共情坐标系；  
与 `edit_craft` 联动后，接缝不只节奏，还有**权力与视线**。

## 代码

| API | 作用 |
|---|---|
| `suggest_focal_character` | beat → 共情归属 |
| `suggest_viewpoint` / `suggest_look_axis` | 机位语法 / 180° |
| `lint_character_stance` | VIEWPOINT_FLAT 等 |
| `apply_coverage_defaults_to_shot` | 注入 + framing 提示 |
| `suggest_edit_craft(..., focal_changed=)` | 立场切换 → contrast/smash |

## 验收

- write-spec 后每镜有 `dsl.viewpoint` / `focal_character`  
- `_character_stance.ok` 或可解释的 soft codes  
- 改立场须 re-I2V
