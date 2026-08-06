# Scene Design Sheet — 场景设计表模板

> P1-5 场景设计 sheet · Location schema 升级
> 每个场景一张完整设计表，含色温动机/陈设/质感/光位/道具锚点。

## 场景：{location_id}

| 字段 | 值 |
|---|---|
| **id** | `loc_rainy_street` |
| **description** | 雨夜城市街道，霓虹灯反射湿地面 |
| **structure** | 纵深巷道，两侧高楼，尽头有出口 |
| **timeOfDay** | night |
| **lighting** | 霓虹冷光+路灯暖光混合，低照度高反差 |
| **palette** | 深蓝/紫/霓虹粉 |
| **color_temperature** | 冷 5600K 霓虹 + 暖 3200K 路灯混合 |
| **atmosphere** | 压抑、潮湿、孤独感 |
| **immutableRules** | 地面始终有水反射/霓虹始终可见/角色始终在阴影侧 |
| **recurringObjects** | 路灯/垃圾桶/霓虹招牌/消防栓 |
| **primaryAngles** | 纵深低机位/侧面高机位/仰拍霓虹 |
| **set_dressing** | 湿地面/散落报纸/积水瓶/远处车灯 |
| **lighting_plot** | 主光=路灯45°暖光；辅光=霓虹冷光漫射；轮廓=背后路灯逆光 |
