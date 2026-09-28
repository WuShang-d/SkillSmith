# SkillSmith 项目报告书

**第三届 NVIDIA DGX Spark Hackathon · Agent Skills 开发挑战赛**

> 把 Agent 的一次成功，锻造成全公司都敢装的能力。

- 演示视频：[B 站观看](https://www.bilibili.com/video/BV1HaaG6QE3f/)（约 2 分钟）
- 应用领域：零售 / 批发（演示场景）；方法适用于任何"跑通过一次"的多模态 Agent 流程
- 运行环境：NVIDIA DGX Spark（GB10）· Qwen3.6-35B-A3B · vLLM · OpenClaw · NVIDIA SkillSpector · OpenSSF model-signing

## 1. 问题

企业里最常见的一幕：同事用 Agent 跑通了一次任务，比如对照陈列图检查门店货架，大家把提示词打包成 Skill，准备推给所有门店。但推之前，没有人答得上四个问题：

| 问题 | 对应能力 |
| --- | --- |
| 装上它，Agent 真的比不装更好吗？ | 公平 A/B 评测 |
| 该用的时候会被用上、不该用的时候不乱用吗？ | 真实 Agent 触发测试 |
| 装进门店的，还是发出去的那一版吗？ | 签名与验签安装 |
| 货架照片、陈列图这些商业数据，能不出本地吗？ | DGX Spark 本地推理 |

NVIDIA 官方目录里的 Skill 由 Verified Skills 流程保证（Scanned · Evaluated · Signed · Documented），但企业自己沉淀的 Skill 进不了官方目录，同样需要这条信任链。

## 2. 方案

SkillSmith 把一次成功的多模态工作流生成标准 Agent Skill，并在安装前强制通过一道发布门禁：

```text
成功工作流 → 生成 Skill → 安全扫描 → 公平 A/B → 真实触发 → 签名 → 验签安装 → 新输入复现
                         └────────────── 发布门禁：任何一关不过就不安装 ──────────────┘
```

1. **生成**：校验工作流规范（正负触发、步骤、护栏、输出契约、正负评测用例），生成 `SKILL.md`、`scripts/run.py`、`references/`、`evals/evals.json`。缺负向用例或成功运行事实时拒绝生成。
2. **安全扫描**：NVIDIA SkillSpector 2.12.0 + SkillSmith 自有规则（危险删除、下载即执行、硬编码密钥、`eval`、`shell=True`、越界写入、双向文本控制字符等）。
3. **公平 A/B**：同一台 DGX、同一模型、同一图片与请求；**对照组拿到相同的输出格式**；按精确真值打分。Skill 附带业务资料时，另加"直接粘贴资料"对照组，Skill 必须不输给它。
4. **真实触发**：每条正负提示在 OpenClaw（20 多个可用 Skill）中作为新会话重复运行 3 次，以 OpenClaw 自己的会话记录是否加载了该 `SKILL.md` 判定。
5. **说明卡与签名**：按 NVIDIA Skill Card 章节自动生成 `skill-card.md` 并附实测证据；用本地根证书按 OpenSSF Model Signing 签发 `skill.oms.sig`，安装前后各验签一次。
6. **复现**：在从未参与评测的新输入上运行已安装 Skill，并用同一评分器打分。

SkillSmith 本身也是一个 Skill（`skills-src/skillsmith/`），Agent 装上它就能把自己的一次成功沉淀为新 Skill 并走门禁；非技术用户可用本地浏览器界面（`python3 -m skillsmith.web`）完成同样流程。核心无第三方 Python 依赖。

## 3. 实测结果（DGX Spark 本地）

同一道门禁，**拦下一个、放行一个**。

| Skill | 不装 | 粘贴资料 | 装 Skill | OpenClaw 触发 | 门禁 |
| --- | ---: | ---: | ---: | --- | --- |
| 零售货架巡检 `retail-shelf-audit` | 82.7% | – | 82.3% | 36/36 | **拦截，不安装** |
| 门店陈列合规 `planogram-compliance` | 11.1% | 72.6% | 78.4% | 35/36 | **通过，签名后验签安装** |

**货架巡检为什么被拦**：安全扫描通过、触发 36/36 全对，但 Qwen3.6 本来就会数排面，装了没有更好。门禁要求严格优于基线（彩排中 82.7% 对 82.7% 持平，同样被拦）。一个不带来提升的 Skill，推到每家店只会占上下文、增加误触发风险。

**陈列合规为什么通过**（6 张场景图，发布版）：

| 指标 | 不装 | 粘贴资料 | 装 Skill |
| --- | ---: | ---: | ---: |
| 任务得分 | 11.1% | 72.6% | **78.4%** |
| 状态判定准确率 | 0% | 77.4% | **87.1%** |
| 偏差识别 F1 | 33.3% | 46.9% | **53.2%** |
| 排面数完全正确 | 0% | 93.5% | **95.0%** |
| 平均延迟 / 输出 token | 18.1 s / 558 | 24.2 s / 748 | 18.7 s / 568 |

差值来源：粘贴资料的模型把"低于目标"一律标为 LOW；Skill 带的门店政策（达到最低排面即 OK）消除了这类误报，且比粘贴资料快约 5 秒、少约 180 个输出 token。

**新输入复现**：未参与评测的 `replay-a12-evening.png` 上，3 个真实偏差全部找出，1 条误报（绿茶 5 个排面、最低 4，被标 LOW），任务得分 88.6%。

**信任链**：
- SkillSpector 判定我们最初生成的 Skill 风险分 100（DO_NOT_INSTALL）：runner 把 `OPENAI_API_KEY` 发到网络、残留 `.pyc`、未声明工具权限。修复后（runner 固定 127.0.0.1、不读环境变量、声明权限）风险分 3，仅 1 条需人工确认权限的 LOW 提示。
- 三种篡改均验签失败、拒绝安装：改动已签名文件、新增文件、攻击者用自有 CA 重签。
- 完整演示（零售拦截 → 陈列合规扫描、评测、签名、安装 → 复现 → 篡改拒装）在 DGX 上端到端 572 秒。

## 4. DGX Spark 上的实现

- **硬件**：NVIDIA DGX Spark，GB10，约 119 GiB 统一内存，ARM64。
- **模型服务**：`scripts/start-vllm-dgx.sh` 以只读方式挂载预装的 Qwen3.6-35B-A3B，vLLM 仅绑定回环地址；GB10 上需 `VLLM_USE_DEEP_GEMM=0` 与 Triton MoE 后端，否则会报 `CUDA_ERROR_INVALID_IMAGE`。
- **数据不出本机**：推理、上百次 A/B 与触发评测、SkillSpector 扫描、签名全部在节点本地完成；端点默认只允许回环地址，远程端点需显式 `--allow-remote-endpoint`。
- **Agent**：OpenClaw 隔离 profile（`scripts/setup-openclaw-dgx.sh`），用于真实触发测试。

## 5. 创新点

1. **会说"不"的发布门禁**：不只证明 Skill 有用，也在实测中拦下一个安全、好找、但没用的 Skill。
2. **"粘贴资料"对照组**：带资料的 Skill 必须赢过"把同样资料贴进提示词"，否则提升不算 Skill 的功劳。
3. **企业自研 Skill 的本地信任链**：对齐 NVIDIA Verified Skills 的扫描、评测、说明卡、签名，全部在一台 DGX Spark 上完成。
4. **对自己的数字诚实**：第一版"23.6% → 100%"因基线不知道输出格式、评分只查字段名而作废，保留记录；残余误报在结果中主动披露。

## 6. 局限与下一步

- 测试场景图为脚本合成，以获得精确真值；接入真实门店照片只需替换评测集，门禁逻辑不变。
- 评测集规模小（每个 Skill 6 张场景图 + 1 张复现图），适合做门禁演示，不足以代表生产分布。
- 陈列合规仍有两类共同错误：第 3 层薯片误标 MISPLACED；"等于最低线"偶尔被标 LOW。
- 下一步：更多行业工作流模板（质检、巡检、单据审核）；Skill 升级时的回归门禁；多个 Skill 共存时的触发冲突检测。

## 7. 复现方法

```bash
# 离线验证（无需模型）
./scripts/verify.sh

# DGX 上启动本地模型并跑完整演示
./scripts/start-vllm-dgx.sh && ./scripts/wait-vllm-dgx.sh
export OPENAI_BASE_URL=http://127.0.0.1:8000/v1 OPENAI_MODEL=Qwen/Qwen3.6-35B-A3B OPENAI_API_KEY=local
./scripts/setup-release-tools-dgx.sh && ./scripts/init-signing-pki.sh
./scripts/demo-dgx.sh
```

## 8. 证据索引

| 内容 | 路径 |
| --- | --- |
| 零售货架巡检：公平 A/B 与 OpenClaw 触发 | `evidence/dgx-2026-09-23/` |
| 陈列合规：三组对照、触发、复现 | `evidence/dgx-2026-09-24/planogram-compliance/` |
| 发布版：签名 Skill、SkillSpector 前后报告、根证书、演示日志 | `evidence/dgx-2026-09-24/release/` |
| 已作废的第一版结果（保留记录） | `evidence/dgx-2026-09-20/` |
| 需求逐条完成审计 | `docs/COMPLETION_AUDIT.md` |
| 路演稿与参赛包装 | `docs/ROADSHOW.md`、`docs/PITCH.md` |

所有演示门店、人物均为虚构；图片为项目生成的无品牌合成素材，来源与哈希见各示例目录下的 `ASSET_NOTES.md`。
