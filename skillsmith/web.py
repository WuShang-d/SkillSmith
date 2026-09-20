from __future__ import annotations

import argparse
import base64
import binascii
import copy
import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .evaluate import benchmark_markdown, evaluate_fixtures
from .endpoint import capture_ab
from .forge import forge
from .install import install
from .security import report, scan
from .spec import load_spec


PAGE = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SkillSmith · 把成功铸造成能力</title>
<style>
:root{--bg:#080b0a;--panel:#111714;--line:#26352c;--green:#76b900;--mint:#c9ff76;--text:#f4f7f5;--muted:#9eaaa3;--bad:#ff6b6b}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 85% -10%,#244214 0,transparent 38%),var(--bg);color:var(--text);font:15px/1.5 ui-sans-serif,system-ui,-apple-system,sans-serif}
main{max-width:1120px;margin:auto;padding:54px 24px 80px}.eyebrow{color:var(--green);letter-spacing:.16em;text-transform:uppercase;font-weight:800}.hero{display:grid;grid-template-columns:1.35fr .65fr;gap:28px;align-items:end;margin-bottom:32px}h1{font-size:clamp(42px,7vw,82px);line-height:.95;margin:12px 0 18px;letter-spacing:-.055em}.lead{color:var(--muted);font-size:18px;max-width:720px}.promise{border-left:2px solid var(--green);padding:8px 0 8px 20px;color:var(--mint)}
.pipeline{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:28px 0}.stage{padding:12px;border:1px solid var(--line);border-radius:10px;background:#0d120f;color:var(--muted)}.stage b{display:block;color:var(--text);font-size:13px}.card{background:linear-gradient(145deg,#121a15,#0d120f);border:1px solid var(--line);border-radius:18px;padding:24px;box-shadow:0 24px 70px #0008}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.wide{grid-column:1/-1}label{display:block;color:var(--muted);font-size:12px;font-weight:700;letter-spacing:.06em;margin-bottom:7px;text-transform:uppercase}input,textarea{width:100%;color:var(--text);background:#080c09;border:1px solid #304035;border-radius:9px;padding:11px 12px;font:inherit;outline:none}input:focus,textarea:focus{border-color:var(--green);box-shadow:0 0 0 3px #76b90022}textarea{min-height:86px;resize:vertical}.hint{font-size:12px;color:#77847c;margin-top:5px}button{margin-top:20px;border:0;border-radius:10px;background:var(--green);color:#071000;font-weight:900;font-size:15px;padding:13px 22px;cursor:pointer}button:disabled{opacity:.45;cursor:wait}
#result{display:none;margin-top:20px}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.metric{border:1px solid var(--line);border-radius:12px;padding:14px;background:#0a0f0c}.metric span{display:block;color:var(--muted);font-size:11px;text-transform:uppercase}.metric strong{font-size:24px;color:var(--mint)}pre{white-space:pre-wrap;background:#070a08;border-radius:10px;padding:14px;color:#c7d1cb;overflow:auto}.error{color:var(--bad)}
@media(max-width:760px){.hero,.grid{grid-template-columns:1fr}.pipeline{grid-template-columns:1fr 1fr}.metrics{grid-template-columns:1fr 1fr}.wide{grid-column:auto}}
</style></head>
<body><main>
<div class="hero"><div><div class="eyebrow">NVIDIA DGX Spark · Agent Skills</div><h1>SkillSmith</h1><div class="lead">把一次成功的多模态工作流，锻造成可触发、可评测、可审计、可复用的 Agent Skill。</div></div><div class="promise">不上传业务图片。凭据不写入 Skill。门禁失败即停止安装。</div></div>
<div class="pipeline"><div class="stage"><b>01 生成</b>Workflow → Skill</div><div class="stage"><b>02 安全</b>扫描危险模式</div><div class="stage"><b>03 评测</b>Baseline A/B</div><div class="stage"><b>04 安装</b>通过才发布</div><div class="stage"><b>05 复现</b>换输入再运行</div></div>
<section class="card"><form id="forge">
<div class="grid">
<div><label>Skill 名称</label><input id="name" value="retail-shelf-audit" pattern="[a-z0-9-]+" required></div>
<div><label>显示名称</label><input id="display" value="零售货架巡检" required></div>
<div class="wide"><label>它完成什么</label><input id="description" value="Inspect a retail shelf image and return visible SKU facings, empty gaps, image quality, and uncertainties as structured JSON." required></div>
<div class="wide"><label>成功运行证据</label><textarea id="summary" required>本地多模态模型已成功盘点货架排面、识别空位，并把不确定观察与可见证据分开。</textarea></div>
<div><label>应当触发 · 每行一条</label><textarea id="triggers" required>审计或巡检一张零售货架照片
统计货架上各 SKU 的可见排面
识别货架空位并输出结构化 JSON</textarea></div>
<div><label>不应触发 · 每行一条</label><textarea id="negative" required>撰写商品营销文案
没有图片时根据库存数据库生成补货单
识别人脸或顾客身份</textarea></div>
<div class="wide"><label>步骤 · 每行“标题 | 指令”</label><textarea id="steps" required>检查输入质量 | 判断清晰度、遮挡和拍摄范围；无法可靠观察时明确标记。
盘点可见排面 | 按可见标签或包装特征分组，只统计像素可证实的排面。
识别空位 | 记录明显空缺区域及相对位置，不把价格牌间隙误判为空位。
输出审计结果 | 返回严格 JSON，给出图片质量、SKU 排面、空位和不确定项。</textarea></div>
<div><label>输出字段 · 逗号分隔</label><input id="fields" value="image_quality,sku_facings,empty_gaps,uncertainties" required></div>
<div><label>正向测试请求</label><input id="positive" value="请审计这张零售货架照片，统计各 SKU 排面并标出空位，返回 JSON。" required></div>
<div class="wide"><label>护栏 · 每行一条</label><textarea id="guardrails" required>只报告图片中可见的证据，不推断画外库存。
不得识别或推断顾客身份和人口属性。
标签不可读时使用视觉描述并写入 uncertainties。
不得输出图片 base64 或运行时凭据。</textarea></div>
<div><label>无 Skill 输出（Baseline）</label><textarea id="baseline" required>The shelf looks mostly full. There may be a gap.</textarea></div>
<div><label>有 Skill 输出</label><textarea id="skillout" required>{"image_quality":"clear","sku_facings":[],"empty_gaps":[],"uncertainties":[]}</textarea></div>
<div class="wide"><label>真实 DGX A/B · 可选图片</label><input id="image" type="file" accept="image/*"><div class="hint">选择图片后，将忽略上面的模拟输出，并由同一台本地模型分别生成 Baseline 与 Skill 输出。</div></div>
<div><label>本地模型端点</label><input id="baseUrl" value="http://127.0.0.1:8000/v1"></div>
<div><label>本地模型名称</label><input id="model" value="Qwen/Qwen3.6-35B-A3B"></div>
<div class="wide"><label>负向测试请求</label><input id="negativePrompt" value="为这款饮料写一段社交媒体营销文案。" required><div class="hint">正确行为是“不调用这个 Skill”。</div></div>
</div><button id="submit" type="submit">开始锻造 Skill</button></form>
<div id="result"><div class="metrics"><div class="metric"><span>安全门禁</span><strong id="security">—</strong></div><div class="metric"><span>触发准确率</span><strong id="trigger">—</strong></div><div class="metric"><span>A/B 提升</span><strong id="delta">—</strong></div><div class="metric"><span>安装状态</span><strong id="installed">—</strong></div></div><pre id="details"></pre></div>
</section></main>
<script>
const lines=id=>document.getElementById(id).value.split('\n').map(x=>x.trim()).filter(Boolean);
document.getElementById('forge').addEventListener('submit',async e=>{e.preventDefault();const b=document.getElementById('submit'),box=document.getElementById('result'),details=document.getElementById('details');b.disabled=true;b.textContent='锻造中…';box.style.display='block';details.className='';details.textContent='正在生成、扫描、评测并安装…';
const fields=document.getElementById('fields').value.split(',').map(x=>x.trim()).filter(Boolean);const steps=lines('steps').map(x=>{const p=x.split('|');return {title:p.shift().trim(),instruction:p.join('|').trim()}});
const spec={schema_version:'1.0',name:document.getElementById('name').value.trim(),display_name:document.getElementById('display').value.trim(),description:document.getElementById('description').value.trim(),license:'Apache-2.0',successful_run_summary:document.getElementById('summary').value.trim(),triggers:lines('triggers'),negative_triggers:lines('negative'),steps,guardrails:lines('guardrails'),output_contract:{format:'json',required_fields:fields},evals:[{id:'positive-demo',prompt:document.getElementById('positive').value.trim(),should_trigger:true,expected_contains:fields,forbidden_contains:['api_key','customer_identity']},{id:'negative-demo',prompt:document.getElementById('negativePrompt').value.trim(),should_trigger:false}]};
try{const payload={spec,fixtures:{'positive-demo':{baseline:document.getElementById('baseline').value,skill:document.getElementById('skillout').value}}};const file=document.getElementById('image').files[0];if(file){const dataUrl=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(reader.error);reader.readAsDataURL(file)});payload.live={image:{name:file.name,data:String(dataUrl).split(',',2)[1]},base_url:document.getElementById('baseUrl').value.trim(),model:document.getElementById('model').value.trim()}}const r=await fetch('/api/forge',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok)throw new Error(d.error||'unknown error');document.getElementById('security').textContent=d.security.toUpperCase();document.getElementById('trigger').textContent=(d.evaluation.trigger_accuracy*100).toFixed(0)+'%';document.getElementById('delta').textContent=(d.evaluation.improvement*100).toFixed(1)+'%';document.getElementById('installed').textContent=d.status==='ok'?'READY':'BLOCKED';details.textContent=JSON.stringify(d,null,2)}catch(err){details.className='error';details.textContent='失败：'+err.message}finally{b.disabled=false;b.textContent='再次锻造'}});
</script></body></html>'''


def forge_submission(payload: dict[str, Any], workspace: Path) -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:10]
    run_root = workspace / "runs" / run_id
    fixture_root = run_root / "fixtures"
    fixture_root.mkdir(parents=True)
    spec_data = copy.deepcopy(payload["spec"])
    live = payload.get("live")
    input_root = run_root / "inputs"
    if live:
        image_data = live.get("image", {})
        filename = Path(str(image_data.get("name", "input-image"))).name
        if Path(filename).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".pgm"}:
            raise ValueError("live input must be a supported image file")
        try:
            raw = base64.b64decode(str(image_data.get("data", "")), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("live image data is invalid") from exc
        if not raw or len(raw) > 12_000_000:
            raise ValueError("live image must be between 1 byte and 12 MB")
        input_root.mkdir()
        (input_root / filename).write_bytes(raw)
        for case in spec_data.get("evals", []):
            if case.get("should_trigger"):
                case["input"] = filename
    spec_path = run_root / "workflow.json"
    spec_path.write_text(json.dumps(spec_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for case_id, outputs in payload.get("fixtures", {}).items():
        if not isinstance(outputs, dict):
            continue
        for mode in ("baseline", "skill"):
            (fixture_root / f"{case_id}.{mode}.txt").write_text(str(outputs.get(mode, "")), encoding="utf-8")

    spec = load_spec(spec_path)
    generated = forge(spec, run_root / "generated")
    security_result = report(scan(generated))
    (generated / "SECURITY_REPORT.json").write_text(
        json.dumps(security_result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    result: dict[str, Any] = {"run_id": run_id, "security": security_result["verdict"]}
    if security_result["verdict"] != "pass":
        return {**result, "status": "blocked", "stage": "security", "findings": security_result["findings"]}

    capture = None
    if live:
        capture = capture_ab(
            generated,
            input_root,
            fixture_root,
            base_url=str(live.get("base_url", "")),
            model=str(live.get("model", "")),
            api_key=os.environ.get("OPENAI_API_KEY", "local"),
        )
    evaluation = evaluate_fixtures(generated, fixture_root)
    (generated / "BENCHMARK.md").write_text(
        benchmark_markdown(evaluation, spec.name, mode="live" if live else "fixture"), encoding="utf-8"
    )
    result["mode"] = "live" if live else "fixture"
    result["evaluation"] = evaluation
    if capture:
        result["capture"] = capture
    if evaluation["verdict"] != "pass":
        return {**result, "status": "blocked", "stage": "evaluation"}

    installed = install(generated, workspace / "skills", force=True)
    return {**result, "status": "ok", "installed": str(installed)}


def make_handler(workspace: Path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/":
                self.send_error(404)
                return
            data = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path != "/api/forge":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 20_000_000:
                    raise ValueError("request too large")
                payload = json.loads(self.rfile.read(length))
                result = forge_submission(payload, workspace)
                code = 200 if result.get("status") == "ok" else 422
            except Exception as exc:
                result = {"error": str(exc)}
                code = 400
            data = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:
            print("[web] " + format % args)

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local SkillSmith guided UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--workspace", default="build/web")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(workspace))
    print(f"SkillSmith UI: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
