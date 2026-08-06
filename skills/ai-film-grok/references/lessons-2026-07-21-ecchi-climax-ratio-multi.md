# Lessons · 成人尺度比例拉高 + 多女主（2026-07-21）

> **P4 语义绑定 · P5 分层 · P1 身份**  
> 用户：内容尺度更大——前戏到进行到高潮完成比例放高；支援多女主。

## 结论

1. **亲密核**（foreplay + act + climax）在 `heat_scale:max` 下默认 **≥60% 镜**；setup ≤25%。  
2. 必须有 **进行（act）** 与 **高潮完成（climax）** 各 ≥1 镜，禁止只脸红眨眼当 max。  
3. **多女主**：每 id 独立 cast master + ≥1 focal 镜 + ≥1 dual；换女主 cut 缝。

## 代码

| 符号 | 位置 |
|---|---|
| `lint_heat_arc` / `apply_heat_phase_defaults` | `edit_policy.py` |
| `lint_multi_heroine` | `edit_policy.py` |
| write-spec 挂载 | `film_spec.validate_film_spec` → `_heat_arc` / `_multi_heroine` |
| 测试 | `tests/test_heat_arc_multi.py` |

## 权威

[ecchi-story.md](ecchi-story.md) §尺度比例 · §多女主 · [hard-defaults.md](hard-defaults.md)
