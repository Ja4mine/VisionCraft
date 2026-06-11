"""Goal clarification agent powered by DeepSeek."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, TypeAlias

from openai import OpenAI

ChatMessage: TypeAlias = dict[str, str]


CLARIFIER_SYSTEM_PROMPT = """
你是一个严苛的学习规划导师。
你的唯一任务是通过提问弄清用户的具体情况，绝对不能直接给出学习计划。

你必须遵守：
1. 不要输出课程表、阶段计划、学习路径、资源清单、每日安排或行动方案。
2. 每轮最多只问一个高价值问题。
3. 优先确认目标边界、当前基础、时间投入、验收标准、偏好方向、约束条件。
4. 当信息足以制定一个极度具体的学习计划时，将 is_clear 设为 true，并停止继续提问。
5. 无论如何，只能返回一个 JSON 对象，不要返回 Markdown，不要包裹代码块，不要输出额外文本。

JSON 对象格式必须严格为：
{
  "is_clear": false,
  "thought_process": "内部判断：当前信息缺口是什么，为什么还需要继续问。",
  "next_question": "向用户提出的下一个问题；如果 is_clear 为 true，则为空字符串。",
  "current_summary": "至今收集到的信息摘要。"
}
""".strip()


@dataclass(frozen=True, slots=True)
class ClarificationExchange:
    """One user answer captured during the clarification loop."""

    question: str
    answer: str


@dataclass(frozen=True, slots=True)
class ClarificationResult:
    """Structured response returned by the LLM clarifier."""

    is_clear: bool
    thought_process: str
    next_question: str
    current_summary: str


class ClarifierError(RuntimeError):
    """Raised when the clarifier cannot produce a valid structured response."""


class ClarificationAgent:
    """Drives goal clarification while suppressing plan-generation behavior."""

    def __init__(
        self,
        client: OpenAI,
        model: str,
        temperature: float = 0.2,
    ) -> None:
        self.client = client
        self.model = model
        self.temperature = temperature

    def evaluate(
        self,
        goal: str,
        exchanges: list[ClarificationExchange] | None = None,
    ) -> ClarificationResult:
        """Ask DeepSeek whether the goal is clear enough and what to ask next."""

        messages = [
            {"role": "system", "content": CLARIFIER_SYSTEM_PROMPT},
            {"role": "user", "content": self._build_user_context(goal, exchanges or [])},
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise ClarifierError("DeepSeek 返回了空响应。")

        return self._parse_result(content)

    def build_initial_messages(
        self,
        goal: str,
        memory_context: str = "",
    ) -> list[ChatMessage]:
        """Create the message history for a new clarification conversation."""

        memory_block = (
            f"\n\n长期记忆（来自用户本地 SQLite，供你判断用户基础与偏好）：\n{memory_context.strip()}"
            if memory_context.strip()
            else ""
        )

        return [
            {"role": "system", "content": CLARIFIER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "请评估下面的学习愿景是否已经足够清晰，可以制定极度具体的学习计划。\n\n"
                    f"原始愿景：{goal.strip()}"
                    f"{memory_block}\n\n"
                    "如果还不够清晰，请只提出一个最关键的追问。"
                ),
            },
        ]

    def evaluate_messages(self, messages: list[ChatMessage]) -> ClarificationResult:
        """Evaluate an ongoing clarification conversation."""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise ClarifierError("DeepSeek 返回了空响应。")

        result = self._parse_result(content)
        messages.append({"role": "assistant", "content": content})
        return result

    def _build_user_context(
        self,
        goal: str,
        exchanges: list[ClarificationExchange],
    ) -> str:
        history = "\n".join(
            f"问题 {index}: {exchange.question}\n回答 {index}: {exchange.answer}"
            for index, exchange in enumerate(exchanges, start=1)
        )
        if not history:
            history = "暂无，当前是第一轮判断。"

        return (
            "请评估下面的学习愿景是否已经足够清晰，可以制定极度具体的学习计划。\n\n"
            f"原始愿景：{goal.strip()}\n\n"
            f"已收集的问答：\n{history}\n\n"
            "如果还不够清晰，请只提出一个最关键的追问。"
        )

    def _parse_result(self, raw_content: str) -> ClarificationResult:
        try:
            payload: dict[str, Any] = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise ClarifierError(f"DeepSeek 未返回合法 JSON：{raw_content}") from exc

        missing_keys = {
            "is_clear",
            "thought_process",
            "next_question",
            "current_summary",
        } - payload.keys()
        if missing_keys:
            missing = ", ".join(sorted(missing_keys))
            raise ClarifierError(f"DeepSeek JSON 缺少字段：{missing}")

        is_clear = payload["is_clear"]
        if not isinstance(is_clear, bool):
            raise ClarifierError("DeepSeek JSON 字段 is_clear 必须是布尔值。")

        return ClarificationResult(
            is_clear=is_clear,
            thought_process=str(payload["thought_process"]).strip(),
            next_question=str(payload["next_question"]).strip(),
            current_summary=str(payload["current_summary"]).strip(),
        )
