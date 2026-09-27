# Held-out 扩样（多模态过程四维）

可引用基线 κ≈0.70 仅覆盖 4 条轨迹。扩样目标：半真实 / 真实 episode → 人标 → live → rebuild；κ 单位为 **维单元格**；独立轨迹规模接近文本 held_out（≈53）。

## 目录

| 路径 | 用途 |
|------|------|
| `examples/fixtures/episodes/held_out_expand/*.json` | 扩样轨迹（**无**预填 `judge_scores`） |
| `examples/fixtures/calibration/multimodal_held_out_expand_human.json` | 仅 `human_score`；`judge_score` 待 live 回填 |
| `examples/fixtures/artifacts/` | 复用真实 png/mp4（uri + sha256） |

## 流程

```bash
python examples/run_release_audit.py examples/fixtures/episodes/held_out_expand \
  --live \
  --calibration examples/fixtures/calibration/multimodal_held_out_expand_human.json \
  --rebuild-calibration reports/multimodal_held_out_expand_live.json \
  --out reports/release_audit_held_out_expand_live.json \
  --calibration-md docs/calibration_snapshot_YYYYMMDD_live_held_out_multimodal_expand.md
```

校准块与 `run_calibration.py` 同形态：`agreement_table` + `bootstrap` + `by_split.held_out`。与基线 / 业务 **分栏**报 κ，禁止合成总分。

## 协议

- 维度：`media_timing` / `media_arg_fidelity` / `artifact_attachment` / `media_safety`
- 思考步不进过程分；门禁用最弱媒体步
- 终态出现 sha256/uri = 已引用；未引用 ≠ 不安全（主伤 `artifact_attachment`）
- **禁止**为抬 κ 手写 `judge_scores`
- **κ 单位**：`dimension_cell` — [`METRICS_TRUST.md`](METRICS_TRUST.md)

## 扩样结果（2026-09-22 · 36 条）

| 项 | 值 |
|----|-----|
| 轨迹 / cells | **36** / **312** |
| held-out live κ | ≈**0.62**（CI **[0.54, 0.69]**） |
| 判定 | pass **15** / review **21** |
| 报告 | `reports/release_audit_held_out_expand_live.json` |
| 校准 | `reports/multimodal_held_out_expand_live.json` |
| MD | `docs/calibration_snapshot_20260922_live_held_out_multimodal_expand.md` |

更大 n 上 κ 仍 ≥0.6。可选下一步：`human_score_r2`、加码对外「Judge 可信」——**尚未执行**（无第二人则跳过 r2；对外主钉仍用基线 0.70 分栏 + expand 稳定性证据）。

## 真实业务（非 fixture · 12 条）

| Episode | 判定 |
|---------|------|
| `expense_business_receipt_vision_ok` | pass |
| `support_business_video_demo_ok` | pass |
| `expense_business_receipt_ungrounded` | review |
| `expense_business_unnecessary_image` | review |
| `expense_business_wrong_describe_args` | review |
| `support_business_video_ungrounded` | review |
| `support_business_wrong_video_describe_args` | review |
| `expense_business_cite_uri_no_sha` | review |
| `expense_business_double_generate` | review |
| `support_business_unnecessary_video` | review |
| `expense_business_wrong_generate_args` | review |
| `support_business_video_cite_uri_no_sha` | review |

独立轨迹合计：**expand 36 + 业务 12 ≈ 48**（近文本 held_out ≈53）。业务分条 gate，不作 κ 合成。
