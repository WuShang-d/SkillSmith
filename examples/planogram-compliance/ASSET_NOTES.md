# Planogram-compliance test scenes

`make_scenes.py` composes every scene from product sprites and bare-shelf
texture cut out of the synthetic `../retail-shelf-audit/shelf-clear.png`
(itself a generated, brandless asset; see that folder's `ASSET_NOTES.md`).
Because each facing is pasted by the script, the ground truth in
`workflow.json` and `scenes/held-out-ground-truth.json` is exact by
construction; statuses follow the store policy in the skill
(0 = OOS, below `min_facings` = LOW, otherwise OK; unplanned SKU on a shelf = MISPLACED).

`reference/planogram-bay-A12.json` and `reference/sku-master.json` describe a
fictional demo store. Regenerate with `pip install pillow && python3 make_scenes.py`;
output is deterministic.

- `scenes/within-tolerance.png` SHA-256 `af838e811a822342317169a0ac000488c3b72fc2f89547540a394a63b9f4ee1b`
- `scenes/tea-oos-water-misplaced.png` SHA-256 `10a9df6f519677e4634b30eed2dbc9d4a330f84a57e5286eda5371a4e404f10b`
- `scenes/cola-low-chips-oos.png` SHA-256 `830a75434f34e99ccfc11de24d5f43b4659f479bae00b34618a79a7b0e1b5c56`
- `scenes/mixed-deviations.png` SHA-256 `b74462177db3b26e301d43d4261f47eee4fc3456bae83109b2359b165f5439d6`
- `scenes/fully-compliant.png` SHA-256 `46a277db601d3d4db102753eb33a3e2242bd09b4cfa6526c63c37ca9ca024976`
- `scenes/cola-oos-tea-low.png` SHA-256 `2325f3da1f8b4020d0407ff64277054a0bae27a3376443dab2fee8330e7cffe9`
- `scenes/replay-a12-evening.png` (held out) SHA-256 `b30634b3ce0b1389ed9f46c9a3b39d630de3033c966b469a08d0f534829e875c`
