---
name: planogram-compliance
description: "Check a shelf photo of store bay A12 against the store's planogram and SKU master, and report each planned SKU as OK, LOW or OOS plus any MISPLACED SKU, using the store's SKU codes. Use when: 检查货架照片是否符合陈列图 / planogram; 巡检 A12 货架的陈列合规、缺货和错放; 按门店 SKU 编码输出每个商品的陈列状态; check a shelf photo against the planogram. Do not use for: 只统计货架排面或空位，不对照陈列图; 根据库存数据库生成补货单但没有图片; 撰写商品营销或促销文案; 识别顾客身份或人口属性."
license: Apache-2.0
allowed-tools: Read Bash(python3 scripts/run.py:*)
permissions: ["network: loopback model endpoint 127.0.0.1 only", "file_read: input image and bundled references", "file_write: user-selected output directory"]
---

# 门店陈列合规巡检

Reproduce the validated workflow summarized in [references/workflow.json](references/workflow.json).

## Reference data

Read these before judging the input; they are the only source of codes, targets and policy data.

- [references/planogram-bay-A12.json](references/planogram-bay-A12.json)
- [references/sku-master.json](references/sku-master.json)

## Trigger boundary

Use this skill when:
- 检查货架照片是否符合陈列图 / planogram
- 巡检 A12 货架的陈列合规、缺货和错放
- 按门店 SKU 编码输出每个商品的陈列状态
- check a shelf photo against the planogram

Do not use this skill when:
- 只统计货架排面或空位，不对照陈列图
- 根据库存数据库生成补货单但没有图片
- 撰写商品营销或促销文案
- 识别顾客身份或人口属性

If required input is missing, ask for it instead of guessing.

## Workflow

1. **加载门店资料** — 读取 references/planogram-bay-A12.json 与 references/sku-master.json；照片不是 A12 货架或资料缺失时停止并说明。
2. **识别 SKU** — 只用 SKU 主数据中的视觉特征把商品映射为 sku_code；无法对应的商品写入 uncertainties，不要自造编码。
3. **逐层数最前排排面** — 货架最上层为 1。一个排面是最前沿的一列；上下叠放的同款商品仍算一个排面，后排不算。
4. **按门店政策判定每个计划 SKU** — 对陈列图中每个 (层, sku_code)：实际 0 个排面为 OOS；大于 0 但低于 min_facings 为 LOW；达到 min_facings 即为 OK——低于 target_facings 但不低于 min_facings 不是偏差，不得标为 LOW。
5. **找出错放** — 某层出现陈列图未给该层安排的 sku_code 时，另起一条 MISPLACED 记录，写明实际排面数；同一 SKU 在其计划层的状态照常判定。
6. **输出合规清单** — 陈列图中的每个计划槽位都必须出现一次，再追加所有 MISPLACED；按输出契约返回严格 JSON。

## Output contract

- Format: `json`
- Required fields: `bay_id`, `items`, `uncertainties`
- Shape: `{"bay_id": "A12", "items": [{"shelf": 1, "sku_code": "...", "observed_facings": 0, "status": "OK|LOW|OOS|MISPLACED"}], "uncertainties": ["..."]}  Shelf 1 is the top shelf.`
- Write generated artifacts only beneath the user-selected output directory.
- Separate visible evidence from inference and report uncertainty explicitly.

## Guardrails

- 只依据图片中可见的排面，不推断画外或遮挡后的库存。
- sku_code 只能来自 SKU 主数据；陈列图和政策只来自技能附带的参考资料。
- 不得识别或推断顾客身份、年龄、性别或行为意图。
- 不得输出输入图片的 base64 数据或任何运行时凭据。

## Execution

With a local OpenAI-compatible multimodal endpoint on this machine, run:

```bash
python3 scripts/run.py --input /absolute/path/to/input --output-dir /absolute/path/to/output --model MODEL_NAME [--port 8000]
```

The runner only connects to `127.0.0.1`, reads no environment variables, and never handles credentials.
