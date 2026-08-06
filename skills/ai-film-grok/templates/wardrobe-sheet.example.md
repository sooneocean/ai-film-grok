# Wardrobe Sheet — 服装设计表模板

> 40 年导演方法论注入 · P1-4 服装设计表
>
> `wardrobe_variants` 从卸装阶梯升级为完整服装设计表。
> 每角 × 每场景/状态 → 服装/配饰/材质/色彩/状态。
> 结构化对象格式（也兼容 legacy 字符串格式）。

---

## 结构

```json
"wardrobe_variants": {
  "hero": {
    "full": {
      "garment": "黑色长款风衣，白衬衫，深灰修身长裤",
      "accessories": ["银色腕表", "黑色皮手套"],
      "material": "wool coat, cotton shirt, leather gloves",
      "color": "black/white/dark gray",
      "state": "full"
    },
    "partial": {
      "garment": "白衬衫染血，风衣脱去",
      "accessories": ["银色腕表"],
      "material": "cotton shirt",
      "color": "white stained red",
      "state": "partial"
    },
    "scene_investigation": {
      "garment": "同 full，加黑色战术手套",
      "accessories": ["银色腕表", "黑色战术手套", "耳机"],
      "material": "wool coat, cotton shirt, tactical leather gloves",
      "color": "black/white",
      "state": "full"
    },
    "ending": {
      "garment": "浅色外套——脱去黑色风衣象征放下执念",
      "accessories": ["银色腕表"],
      "material": "light cotton jacket",
      "color": "beige/cream",
      "state": "full"
    }
  }
}
```

## 设计原则

1. **角色×场景**：同一角色在不同场景可有不同服装（不仅是卸装阶梯）。
2. **配饰归属**：配饰必须明确归属角色，跨镜头不可无故消失或增加。
3. **材质锁定**：材质影响光泽与质感，是 continuity 杀手。
4. **色彩锁定**：与 `hair_swatches` 配色协调，与 `cast_locks.never_tokens` 不冲突。
5. **状态标注**：`state` 字段标注 full/partial/undressed/bare，与 `wardrobe_state` 阶梯一致。
6. **象征性**：服装变化可承载角色弧光（如结局脱黑=放下执念）。

## 与卸装阶梯的关系

原有 `wardrobe_variants` 按 `wardrobe_state`（full→bare 单调阶梯）组织，主要服务成人内容。
升级后支持场景级服装变体（`scene_xxx` key），不限于卸装方向。
卸装阶梯逻辑（`WARDROBE_LADDER` rank + reDress 闸）保持不变。
