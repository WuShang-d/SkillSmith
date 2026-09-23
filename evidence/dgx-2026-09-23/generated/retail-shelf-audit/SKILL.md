---
name: retail-shelf-audit
description: "Inspect a retail shelf photo and return front-row SKU facings per shelf, empty gaps, image quality, and uncertainties as structured JSON. Use when: 审计或巡检一张零售货架照片; 统计货架上各 SKU 的可见排面; 识别货架空位并输出结构化 JSON; audit a retail shelf image. Do not use for: 撰写商品营销文案; 根据库存数据库生成补货单但没有图片; 识别人脸、顾客身份或人口属性."
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

1. **检查输入质量** — 先判断图片清晰度、遮挡和拍摄范围；标出被遮挡的层和位置，不补猜画外或遮挡后的内容。
2. **逐层划分货架** — 从上到下给货架层编号，最上层为 1；逐层、从左到右处理，不要跨层合并。
3. **只数最前排排面** — 一个排面是货架最前沿的一列商品。上下叠放的同款商品仍算一个排面，后排露出的瓶盖或罐顶不算新排面。只统计能从像素证实的列。
4. **排除非货架商品** — 购物车、周转箱、推车或手中的商品不是货架排面，不得计入；如有，写入 uncertainties。
5. **识别空位** — 只有露出空隔板、宽度至少能放下一个排面的连续区域才算空位；价签间隙、商品之间的正常缝隙不算。记录空位所在层和左/中/右位置。
6. **输出审计结果** — 按输出契约返回严格 JSON；被遮挡的层只报告可见排面，并在 uncertainties 中说明遮挡的层和位置。

## Output contract

- Format: `json`
- Required fields: `image_quality`, `sku_facings`, `empty_gaps`, `uncertainties`
- Shape: `{"image_quality": {"usable": true, "issues": ["..."]}, "sku_facings": [{"shelf": 1, "sku": "colour + package type", "facings": 0}], "empty_gaps": [{"shelf": 1, "position": "left|center|right", "approx_facings": 0}], "uncertainties": ["..."]}  Shelf 1 is the top shelf.`
- Write generated artifacts only beneath the user-selected output directory.
- Separate visible evidence from inference and report uncertainty explicitly.

## Guardrails

- 只报告图片中可见的证据，不推断画外或遮挡后的库存。
- 不得识别或推断顾客身份、年龄、性别、国籍或行为意图。
- 标签不可读时使用可复核的视觉描述（颜色＋包装类型），并写入 uncertainties。
- 不得输出输入图片的 base64 数据或任何运行时凭据。

## Execution

For a local OpenAI-compatible multimodal endpoint, run:

```bash
python3 scripts/run.py --input /absolute/path/to/input --output-dir /absolute/path/to/output
```

The runner reads `OPENAI_BASE_URL`, `OPENAI_MODEL`, and optionally `OPENAI_API_KEY`. Never print credentials.
