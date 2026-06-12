"""Learning plan generation powered by DeepSeek."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from openai import OpenAI


PLAN_GENERATOR_SYSTEM_PROMPT = """
你是 VisionCraft Aura 的学习计划生成器。
你会基于已经澄清完成的用户目标，生成一份高度具体、可执行、可追踪的 Markdown 学习计划。

你必须遵守：
1. 只输出 Markdown，不要输出 JSON，不要包裹代码块。
2. 计划必须匹配用户当前基础、时间投入、偏好方向和长期记忆。
3. 如果目标涉及红队、C2、攻击性程序、免杀、持久化、漏洞利用或恶意软件相关内容，必须将计划限定为授权实验室、CTF、靶场、防御研究、检测工程和安全架构学习；不要提供真实目标攻击、免杀绕过、隐蔽持久化、恶意代码投放、规避检测或未授权入侵步骤。
4. 对高风险目标，用安全替代目标表达：Windows/macOS 系统原理、网络协议、EDR/AV 检测原理、日志与遥测、实验室内 toy agent 架构、防御验证与检测规则编写。
5. 计划要能用于后续每日打卡，因此任务必须具体到可检查。
6. 如果用户长期表现出拖延或中断，降低初始难度和每日负担。
7. 每个可执行子任务必须标注 `sequence_day: N` 和 `energy_level: 1-5`，不要绑定自然日期。
8. 高认知负荷任务使用 energy_level 4-5，低摩擦复习/阅读/整理任务使用 energy_level 1-2。

Markdown 结构必须包含：
# <目标名称>
## 目标画像
## 资料来源地图
## 难度与节奏
## 阶段路线图
## 每周安排
## 今日启动任务
## 检查点与验收标准
## 调整规则

任务格式示例：
- [ ] sequence_day: 1 | energy_level: 2 | 阅读 Microsoft Learn 的 Windows 进程基础并写 5 条笔记
- [ ] sequence_day: 3 | energy_level: 5 | 在授权实验室中分析一段样例遥测并总结检测点
""".strip()


@dataclass(frozen=True, slots=True)
class GeneratedPlan:
    """A generated Markdown plan and where it was stored."""

    title: str
    markdown: str
    output_path: Path


class PlanGenerationError(RuntimeError):
    """Raised when the plan generator cannot produce a usable plan."""


class PlanGenerator:
    """Turns clarified goals into Markdown learning plans."""

    def __init__(
        self,
        client: OpenAI,
        model: str,
        output_dir: Path | None = None,
        temperature: float = 0.4,
    ) -> None:
        self.client = client
        self.model = model
        self.output_dir = output_dir or Path("plans")
        self.temperature = temperature

    def generate(
        self,
        goal: str,
        clarified_summary: str,
        memory_context: str = "",
        learning_habits: str = "",
        resources_context: str = "",
    ) -> GeneratedPlan:
        """Generate a Markdown plan, save it locally, and return metadata."""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": PLAN_GENERATOR_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": self._build_user_prompt(
                        goal=goal,
                        clarified_summary=clarified_summary,
                        memory_context=memory_context,
                        learning_habits=learning_habits,
                        resources_context=resources_context,
                    ),
                },
            ],
            temperature=self.temperature,
        )
        markdown = response.choices[0].message.content
        if not markdown or not markdown.strip():
            raise PlanGenerationError("DeepSeek 返回了空学习计划。")

        clean_markdown = markdown.strip()
        output_path = self._write_plan(goal, clean_markdown)
        return GeneratedPlan(
            title=self._extract_title(clean_markdown, goal),
            markdown=clean_markdown,
            output_path=output_path,
        )

    def build_output_filename(self, goal_name: str) -> str:
        normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "_", goal_name.lower().strip())
        normalized = normalized.strip("_")[:60]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{normalized or 'learning_goal'}_{timestamp}_readme.md"

    def _build_user_prompt(
        self,
        goal: str,
        clarified_summary: str,
        memory_context: str,
        learning_habits: str,
        resources_context: str,
    ) -> str:
        return (
            "请基于以下信息生成 Markdown 学习计划。\n\n"
            f"原始目标：\n{goal.strip()}\n\n"
            f"澄清后的目标摘要：\n{clarified_summary.strip()}\n\n"
            f"长期记忆：\n{memory_context.strip() or '暂无'}\n\n"
            f"学习习惯状态：\n{learning_habits.strip() or '暂无'}\n\n"
            f"已检索到的学习资料：\n{resources_context.strip() or '暂无'}\n\n"
            "请让计划从今天就能开始执行，并确保每个阶段都有明确产出。"
            "如果提供了学习资料，请在“资料来源地图”和各阶段中引用这些链接；"
            "如果资料不足，请明确标注需要补充检索的主题。"
        )

    def _write_plan(self, goal: str, markdown: str) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / self.build_output_filename(goal)
        output_path.write_text(markdown + "\n", encoding="utf-8")
        return output_path

    def _extract_title(self, markdown: str, fallback: str) -> str:
        for line in markdown.splitlines():
            if line.startswith("# "):
                return line.removeprefix("# ").strip()
        return fallback.strip() or "学习计划"
