---
name: retail-shelf-audit
description: "Inspect a retail shelf image and return visible SKU facings, empty gaps, image quality, and uncertainties as structured JSON. Use when: 审计或巡检一张零售货架照片; 统计货架上各 SKU 的可见排面; 识别货架空位并输出结构化 JSON; audit a retail shelf image. Do not use for: 撰写商品营销文案; 根据库存数据库生成补货单但没有图片; 识别人脸、顾客身份或人口属性."
license: Apache-2.0
---

# 零售货架巡检

Reproduce the validated workflow summarized in [references/workflow.json](references/workflow.json).

## Trigger boundary

Use this skill when:
- 审计或巡检一张零售货架照片
- 统计货架上各 SKU 的可见排面
- 识别货架空位并输出结构化 JSON
- audit a retail shelf image

Do not use this skill when:
- 撰写商品营销文案
- 根据库存数据库生成补货单但没有图片
- 识别人脸、顾客身份或人口属性

If required input is missing, ask for it instead of guessing.

## Workflow

1. **检查输入质量** — 先判断图片清晰度、遮挡和拍摄范围；无法可靠观察时明确标记，不补猜画外内容。
2. **盘点可见排面** — 按可见标签或包装特征分组，只统计能够从像素证实的 SKU 排面数量。
3. **识别空位** — 记录货架上明显连续的空缺区域及其相对位置，不把价格牌间隙误判为空位。
4. **输出审计结果** — 返回严格 JSON，分别给出图片质量、SKU 排面、空位和不确定项。

## Output contract

- Format: `json`
- Required fields: `image_quality`, `sku_facings`, `empty_gaps`, `uncertainties`
- Write generated artifacts only beneath the user-selected output directory.
- Separate visible evidence from inference and report uncertainty explicitly.

## Guardrails

- 只报告图片中可见的证据，不推断画外库存。
- 不得识别或推断顾客身份、年龄、性别、国籍或行为意图。
- 标签不可读时使用可复核的视觉描述，并写入 uncertainties。
- 不得输出输入图片的 base64 数据或任何运行时凭据。

## Execution

For a local OpenAI-compatible multimodal endpoint, run:

```bash
python3 scripts/run.py --input /absolute/path/to/input --output-dir /absolute/path/to/output
```

The runner reads `OPENAI_BASE_URL`, `OPENAI_MODEL`, and optionally `OPENAI_API_KEY`. Never print credentials.
