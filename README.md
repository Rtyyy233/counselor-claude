# Counselor Claude / 心理咨询师 Claude

基于 [Counselor-Agent](https://github.com/RTyyyy/Counselor-Agent) 的 Claude Code 移植版。由 Claude Code 直接担任整合式心理咨询师，负责对话、个案概念化、治疗计划制定与跟踪。延续原项目的 15 个治疗技能体系、14 领域用户画像系统和 Chroma 向量数据库。

A Claude Code port of [Counselor-Agent](https://github.com/RTyyyy/Counselor-Agent). Claude Code directly serves as the therapist — conducting sessions, formulating treatment plans, and tracking continuity across sessions. Preserves the original project's 15-skill therapy framework, 14-domain profile system, and Chroma database.

---

## 项目架构 / Architecture

```
counselor-claude/
├── CLAUDE.md                  # 治疗师人格、会话协议、跨会话连续性 / therapist persona & session protocols
├── skills/
│   ├── therapy/               # 15 个治疗技能（按需加载）
│   │   ├── INDEX.md           #   技能目录 + 触发条件
│   │   ├── person-centered.md #   人本中心（底色，始终在场）
│   │   ├── existential.md     #   存在主义
│   │   ├── psychodynamic.md   #   精神分析/心理动力学
│   │   ├── adlerian.md        #   阿德勒疗法
│   │   ├── gestalt.md         #   格式塔疗法
│   │   ├── cbt.md             #   认知行为疗法
│   │   ├── behavioral-third-wave.md  # 第三波行为疗法 (DBT/ACT/MBSR)
│   │   ├── choice-reality.md  #   选择理论/现实疗法
│   │   ├── sfbt.md            #   焦点解决短程疗法
│   │   ├── narrative.md       #   叙事疗法
│   │   ├── feminist.md        #   女权主义疗法
│   │   ├── family-systems.md  #   家庭系统疗法
│   │   ├── alliance-repair.md #   治疗联盟修复
│   │   ├── clinical-interviewing.md  # 临床面谈技术
│   │   └── crisis-intervention.md    # 危机干预
│   └── supervision/           # 5 个自我监测技能（治疗师自我督导）
│       ├── INDEX.md
│       ├── alliance-monitoring.md    # 联盟监测
│       ├── process-quality.md        # 过程质量
│       ├── countertransference.md    # 反移情监测
│       ├── pattern-recognition.md    # 模式识别
│       └── crisis-detection.md       # 危机检测
├── tools/
│   └── db.py                  # 数据库桥梁：检索 / 查看画像 / 查看计划 / 存储
├── memory/
│   ├── MEMORY.md              # Claude Code 原生 memory 索引
│   └── session-state.md       # 跨重启会话状态（阶段、目标、pending items）
├── database/                  # 数据目录
│   ├── (Chroma SQLite)        #   向量数据库：原始日记、PAIP摘要、材料
│   ├── profiles/              #   用户画像 JSON（14 领域 + 版本快照）
│   └── treatment_plans/       #   治疗计划 JSON（4 阶段 + 进度追踪）
├── requirements.txt
└── README.md
```

### 核心设计 / Core Design

**治疗师直接承担所有角色。** 不需要 LangChain Agent、不需要独立的 Supervisor、不需要 DeepSeek。Claude Code 在对话中同时完成共情回应和自我监测。技能文件按需加载——先读 INDEX 看触发条件，再精准打开匹配的那一个，而不是把所有内容塞进 prompt。

**The therapist handles everything.** No separate agents. Claude Code empathizes with the client while self-monitoring alliance quality, process quality, and plan fidelity in the same turn. Skills are loaded on demand — read the INDEX for trigger conditions, then open the specific `.md` file that matches, rather than pre-loading all 15 into context.

**跨会话治疗连续性。** 每次启动自动加载：上次会话状态（`memory/session-state.md`）、治疗计划（`database/treatment_plans/`）、用户画像（`database/profiles/`）、最近 PAIP 摘要（Chroma）。会话中每 3-5 轮自动存储 PAIP。会话结束时更新状态、计划、画像。

**Cross-session continuity.** On startup, automatically loads: last session state, treatment plan, user profile, recent PAIP summaries. Stores updated PAIP every 3-5 turns during session. Updates state, plan, and profile at session end.

---

## 安装 / Setup

### 前置条件 / Prerequisites

- [Claude Code](https://claude.ai/code)
- Python 3.11+ / `pip`
- [Ollama](https://ollama.com) + `qwen3-embedding:4b`（向量检索 / vector search）
- DeepSeek API key（仅用于 `store-paip` 的 PAIP 摘要生成 / only for PAIP summary generation）

### 安装 / Install

```bash
git clone <repo-url>
cd counselor-claude
pip install -r requirements.txt

# 配置数据库路径：复制旧数据库，或从零开始
cp -r /path/to/Counselor-Agent-main/database ./database/
# 或者 / or:
mkdir -p database/profiles/default

# 创建 .env
echo 'DEEPSEEK_API_KEY=your-key' > .env
echo 'DATA_DIR=database' >> .env
```

### 使用 / Usage

```bash
cd counselor-claude
claude
```

直接开始对话。Claude Code 自动加载治疗师角色，处理会话连续性、技能选择、数据库查询。

Start talking. Claude Code loads the therapist persona and handles everything automatically.

---

## 数据库命令 / Database Commands

```bash
# 检索 / Search
python tools/db.py search --source diary    --query "焦虑 躯体化"
python tools/db.py search --source conv     --query "来访者主诉"
python tools/db.py search --source material --query "认知行为疗法"
python tools/db.py search --source all      --query "核心困扰"

# 查看 / View
python tools/db.py profile-view [--user default] [--domain 1,5,8]
python tools/db.py plan-view [--user default]

# 存储 / Store
python tools/db.py store-paip --text "PAIP summary..."
python tools/db.py store-diary --file /path/to/diary.txt
python tools/db.py store-material --file /path/to/material.txt
```

### Chroma 集合 / Collections

| Collection | 内容 / Content | 填充 / Populated by |
|-----------|-------|-------------------|
| `original_diary` | 原始日记 / raw diary | `store-diary` |
| `conv_outline` | PAIP 摘要 + 原始对话 / PAIP + raw conversation | `store-paip` |
| `child_chunks` | 材料语义块 / material chunks | `store-material` |
| `parent_chunks` | 材料全文 / material full text | `store-material` |
| `user_profile` | 画像快照 / profile snapshot | 画像保存时自动写入 |

---

## 移植给别人 / Porting

1. 分享仓库 / Share the repository
2. 安装依赖 `pip install -r requirements.txt`
3. 复制 `database/` 目录（含所有来访者数据、画像、计划）
4. 进入目录，启动 Claude Code

不需要启动任何服务。完全自包含。
No servers. Fully self-contained.
