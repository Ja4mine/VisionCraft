# VisionCraft
A Personalized Vision Breakdown and Planning System

## MVP Directory Structure

```text
VisionCraft/
├── plans/                         # Generated Markdown learning plans
├── src/
│   └── aura/
│       ├── agents/                # Clarification and plan-generation agents
│       ├── core/                  # Shared services such as LLM clients
│       ├── storage/               # SQLite-backed local state management
│       ├── config.py              # Local DeepSeek configuration
│       └── main.py                # Typer CLI entrypoint
├── pyproject.toml                 # Local package and aura command entrypoint
└── requirements.txt
```

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
aura init
aura config
aura config --show
aura goal add "我想系统学习密码学"
aura goal add "我想系统学习密码学" --no-plan
aura plan generate
aura plan generate --no-web
aura daily
aura daily --no-adjust
aura memory show
aura obsidian config --vault "/path/to/ObsidianVault"
aura obsidian sync
aura plan metadata --plan-id 1 --category red-team --priority 1 --importance 5
```

Aura 会使用本地 SQLite 保存目标澄清会话、每轮提问回答、用户画像摘要和学习习惯。
后续调用 `aura goal add` 时，这些长期记忆会被注入给 Clarification Agent，帮助模型理解你的基础、偏好和历史上下文。

当目标信息收集完毕后，Aura 会自动生成 Markdown 学习计划，在终端渲染预览，并保存到 `plans/` 目录。
如果你已经完成了目标拆解，也可以运行 `aura plan generate`，基于最近一次澄清会话和长期记忆补生成计划。
计划生成默认会联网检索公开学习资料，并把资料来源注入给 Plan Generator；如果只想使用本地画像，可以加 `--no-web`。

每天运行 `aura daily` 进行打卡。Aura 会读取当前 active 计划、近期打卡和学习习惯，让 AI 动态生成调整后的后续计划；如果只想记录进度，可以加 `--no-adjust`。

配置 Obsidian vault 后，Aura 会把新生成或调整后的计划自动同步到 `VisionCraft/Plans`，并维护 `VisionCraft Plan Index.md` 索引页。每个计划都会带 YAML frontmatter，包含分类、状态、优先级和重要性，方便在 Obsidian 或 Dataview 中管理。
