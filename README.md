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
aura goal add "我想系统学习数学"
aura goal add "我想系统学习数学" --no-plan
aura goal resume --draft-id 1
aura plan generate
aura plan generate --draft-id 1
aura plan generate --no-web
aura daily
aura daily --no-adjust
aura tree
aura tree --regenerate
aura memory show
aura obsidian config --vault "/path/to/ObsidianVault"
aura obsidian sync
aura plan metadata --plan-id 1 --category red-team --priority 1 --importance 5
aura reset
aura reset --yes --include-config --include-obsidian
```

Aura 会使用本地 SQLite 保存目标澄清会话、每轮提问回答、用户画像摘要和学习习惯。
后续调用 `aura goal add` 时，这些长期记忆会被注入给 Clarification Agent，帮助模型理解你的基础、偏好和历史上下文。

当目标信息收集完毕后，Aura 会自动生成 Markdown 学习计划，在终端渲染预览，并保存到 `plans/` 目录。
如果你已经完成了目标拆解，也可以运行 `aura plan generate`，基于最近一次澄清会话和长期记忆补生成计划。
计划生成默认会联网检索公开学习资料，并把资料来源注入给 Plan Generator；如果只想使用本地画像，可以加 `--no-web`。

目标拆解默认最多连续追问 15 轮。如果达到上限，Aura 会保存草稿并提示 `aura goal resume --draft-id <id>`。你也可以用 `aura plan generate --draft-id <id>` 基于草稿摘要和对话上下文补生成计划。

每天运行 `aura daily` 进行打卡。Aura 会读取当前 active 计划、近期打卡和学习习惯，让 AI 动态生成调整后的后续计划；如果只想记录进度，可以加 `--no-adjust`。

Aura 的每日调度不使用“逾期任务”。计划任务会绑定到 `Sequence Day N`，而不是自然日期。几天没打卡后再次运行 `aura daily`，系统会静默顺延并用温和的方式从上次序列继续。

`aura daily` 的第一个交互会询问今日精力 `1-5`，随后只推荐 `energy_level <= 今日精力` 的任务。计划生成时每个可执行任务都会被要求标注 `sequence_day` 和 `energy_level`。

运行 `aura tree` 可以把当前计划渲染为目标拓扑。Aura 会先判断目标是探索型学习 `learning_divergent` 还是交付型任务 `task_convergent`：前者用发散技能树展示，后者用收束里程碑管道展示。已完成节点为绿色 `[✓]`，进行中节点为蓝色，锁定节点为暗灰色。

配置 Obsidian vault 后，Aura 会把新生成或调整后的计划自动同步到 `VisionCraft/Plans`，并维护 `VisionCraft Plan Index.md` 索引页。每个计划都会带 YAML frontmatter，包含分类、状态、优先级和重要性，方便在 Obsidian 或 Dataview 中管理。

运行 `aura reset` 可以格式化 Aura：清空 SQLite 历史、生成计划和 Python 缓存。默认保留 API Key 与 Obsidian 配置；如果需要完全清空，可以加 `--include-config`，如果也要删除 Obsidian 中的 Aura 导出目录，可以加 `--include-obsidian`。
