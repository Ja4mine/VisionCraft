"""Typer CLI entrypoint for Aura."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import IntPrompt

from aura import __version__
from aura.agents.clarifier import (
    ChatMessage,
    ClarificationAgent,
    ClarificationResult,
    ClarifierError,
)
from aura.agents.plan_generator import (
    GeneratedPlan,
    PlanGenerationError,
    PlanGenerator,
)
from aura.agents.resource_researcher import ResourceResearcher
from aura.agents.scheduler import (
    HumanCentricScheduler,
    SchedulerError,
    SchedulerTask,
)
from aura.agents.tracker import (
    AdjustedPlan,
    CheckInReport,
    DailyTracker,
    TrackerError,
)
from aura.config import ConfigManager
from aura.core.input import TerminalInput
from aura.core.llm_client import DeepSeekClientFactory
from aura.core.obsidian import ObsidianExporter
from aura.storage.state_manager import StateManager
from aura.topology.generator import (
    TopologyError,
    TopologyGenerator,
    parse_topology,
)
from aura.topology.renderer import TopologyRenderer


class AuraCLI:
    """Wires command handlers to Typer while keeping services injectable."""

    def __init__(
        self,
        config_manager: ConfigManager | None = None,
        state_manager: StateManager | None = None,
        console: Console | None = None,
        terminal_input: TerminalInput | None = None,
    ) -> None:
        self.config_manager = config_manager or ConfigManager()
        self.state_manager = state_manager or StateManager()
        self.console = console or Console()
        self.terminal_input = terminal_input or TerminalInput()
        self.app = typer.Typer(
            name="aura",
            help="VisionCraft Aura: 一个命令行学习规划助手。",
            no_args_is_help=True,
        )
        self.goal_app = typer.Typer(
            name="goal",
            help="管理学习愿景与目标拆解。",
            no_args_is_help=True,
        )
        self.memory_app = typer.Typer(
            name="memory",
            help="查看 Aura 的本地长期记忆。",
            no_args_is_help=True,
        )
        self.plan_app = typer.Typer(
            name="plan",
            help="基于已澄清画像生成学习计划。",
            no_args_is_help=True,
        )
        self.obsidian_app = typer.Typer(
            name="obsidian",
            help="同步学习计划到 Obsidian vault。",
            no_args_is_help=True,
        )
        self._register_commands()

    def _register_commands(self) -> None:
        self.app.callback()(self._version_callback)
        self.app.command("config")(self.config)
        self.app.command("init")(self.init)
        self.app.command("daily")(self.daily)
        self.app.command("tree")(self.tree)
        self.goal_app.command("add")(self.goal_add)
        self.app.add_typer(self.goal_app, name="goal")
        self.memory_app.command("show")(self.memory_show)
        self.app.add_typer(self.memory_app, name="memory")
        self.plan_app.command("generate")(self.plan_generate)
        self.plan_app.command("metadata")(self.plan_metadata)
        self.app.add_typer(self.plan_app, name="plan")
        self.obsidian_app.command("config")(self.obsidian_config)
        self.obsidian_app.command("sync")(self.obsidian_sync)
        self.app.add_typer(self.obsidian_app, name="obsidian")

    def _version_callback(
        self,
        version: Annotated[
            bool,
            typer.Option("--version", help="显示当前版本。"),
        ] = False,
    ) -> None:
        if version:
            self.console.print(f"aura {__version__}")
            raise typer.Exit()

    def config(
        self,
        api_key: Annotated[
            str | None,
            typer.Option("--api-key", "-k", help="DeepSeek API Key。"),
        ] = None,
        show: Annotated[
            bool,
            typer.Option("--show", help="显示当前配置状态，不显示完整 API Key。"),
        ] = False,
    ) -> None:
        """Configure the DeepSeek API Key used by Aura."""

        if show:
            settings = self.config_manager.load()
            self.console.print(
                Panel.fit(
                    f"配置文件: {self.config_manager.config_path}\n"
                    f"API Key: {settings.masked_api_key}\n"
                    f"Base URL: {settings.base_url}\n"
                    f"Model: {settings.model}\n"
                    f"Obsidian Vault: {settings.obsidian_vault_path or '未配置'}\n"
                    f"Obsidian Folder: {settings.obsidian_folder}",
                    title="Aura 配置",
                )
            )
            return

        provided_key = api_key or self.terminal_input.ask(
            "请输入 DeepSeek API Key",
            password=True,
        )
        if not provided_key.strip():
            self.console.print("[red]API Key 不能为空。[/red]")
            raise typer.Exit(code=1)

        settings = self.config_manager.update_api_key(provided_key)
        self.console.print(
            Panel.fit(
                f"DeepSeek API Key 已保存: {settings.masked_api_key}\n"
                f"配置文件: {self.config_manager.config_path}",
                title="配置成功",
                border_style="green",
            )
        )

    def init(self) -> None:
        """Initialize local state storage for Aura."""

        self.state_manager.initialize()
        self.console.print(
            Panel.fit(
                "本地状态数据库已准备好。\n"
                "下一步可以运行 `aura config` 配置 DeepSeek API Key。",
                title="Aura 初始化完成",
                border_style="green",
            )
        )

    def goal_add(
        self,
        goal: Annotated[
            str | None,
            typer.Argument(help="你想学习或达成的模糊愿景。"),
        ] = None,
        max_questions: Annotated[
            int,
            typer.Option("--max-questions", "-m", help="最多允许 Aura 连续追问的轮数。"),
        ] = 8,
        debug: Annotated[
            bool,
            typer.Option("--debug", help="显示 Clarification Agent 的内部判断。"),
        ] = False,
        no_plan: Annotated[
            bool,
            typer.Option("--no-plan", help="只完成目标拆解，不生成学习计划。"),
        ] = False,
        web: Annotated[
            bool,
            typer.Option("--web/--no-web", help="生成计划前是否联网检索学习资料。"),
        ] = True,
    ) -> None:
        """Add a goal and clarify it through a strict question-only agent."""

        raw_goal = goal or self.terminal_input.ask("你想学习什么，或想达成什么愿景")
        if self._is_exit_command(raw_goal):
            self.console.print("[yellow]已取消添加目标。[/yellow]")
            raise typer.Exit()
        if not raw_goal.strip():
            self.console.print("[red]学习愿景不能为空。[/red]")
            raise typer.Exit(code=1)
        if max_questions < 1:
            self.console.print("[red]--max-questions 必须大于 0。[/red]")
            raise typer.Exit(code=1)

        settings = self.config_manager.load()
        if not settings.has_api_key:
            self.console.print("[red]DeepSeek API Key 尚未配置，请先运行 `aura config`。[/red]")
            raise typer.Exit(code=1)

        client = DeepSeekClientFactory(settings).create()
        clarifier = ClarificationAgent(client=client, model=settings.model)
        memory_context = self.state_manager.build_memory_context()
        messages = clarifier.build_initial_messages(raw_goal, memory_context=memory_context)
        session_id = self.state_manager.create_clarification_session(raw_goal)
        current_summary = ""

        self.console.print(
            Panel.fit(
                "Aura 会先追问关键信息。在信息足够前，它不会生成学习计划。\n"
                "你可以随时输入 `exit` 或 `quit` 保存当前对话并退出。",
                title="目标拆解开始",
                border_style="cyan",
            )
        )

        try:
            question_index = 0
            result = self._request_clarification(clarifier, messages)
            while True:
                current_summary = result.current_summary
                self.state_manager.update_clarification_session(
                    session_id=session_id,
                    current_summary=current_summary,
                    status="active",
                )
                self._render_clarification_result(result, debug=debug)
                if result.is_clear:
                    self.state_manager.update_clarification_session(
                        session_id=session_id,
                        current_summary=current_summary,
                        status="clarified",
                    )
                    self.state_manager.update_user_profile_from_summary(current_summary)
                    self._render_ready_summary(result.current_summary)
                    if no_plan:
                        return

                    generated_plan = self._generate_plan(
                        client=client,
                        model=settings.model,
                        session_id=session_id,
                        goal=raw_goal,
                        summary=current_summary,
                        memory_context=memory_context,
                        web=web,
                    )
                    self._render_generated_plan(generated_plan)
                    return

                if question_index >= max_questions:
                    self.state_manager.update_clarification_session(
                        session_id=session_id,
                        current_summary=current_summary,
                        status="max_questions_reached",
                    )
                    draft_id = self._save_goal_draft(raw_goal, messages, current_summary, "max_questions_reached")
                    self.console.print(
                        Panel.fit(
                            f"已达到最大追问轮数，当前对话已保存为草稿 #{draft_id}。",
                            title="目标拆解暂停",
                            border_style="yellow",
                        )
                    )
                    return

                if not result.next_question:
                    raise ClarifierError("DeepSeek 判断信息不足，但没有给出下一个问题。")

                question_index += 1
                self._render_next_question(result.next_question, question_index)
                answer = self.terminal_input.ask("你的回答")
                if self._is_exit_command(answer):
                    self.state_manager.update_clarification_session(
                        session_id=session_id,
                        current_summary=current_summary,
                        status="interrupted",
                    )
                    draft_id = self._save_goal_draft(raw_goal, messages, current_summary, "interrupted")
                    self.console.print(
                        Panel.fit(
                            f"当前对话已保存为草稿 #{draft_id}，你可以之后继续完善这个目标。",
                            title="已保存并退出",
                            border_style="yellow",
                        )
                    )
                    return

                self.state_manager.record_question_answer(
                    session_id=session_id,
                    goal=raw_goal,
                    question=result.next_question,
                    answer=answer,
                )
                messages.append(
                    {
                        "role": "user",
                        "content": f"你刚才的问题是：{result.next_question}\n我的回答是：{answer.strip()}",
                    }
                )
                result = self._request_clarification(clarifier, messages)
        except KeyboardInterrupt:
            self.state_manager.update_clarification_session(
                session_id=session_id,
                current_summary=current_summary,
                status="interrupted",
            )
            draft_id = self._save_goal_draft(raw_goal, messages, current_summary, "interrupted")
            self.console.print(
                Panel.fit(
                    f"检测到中断，当前对话已保存为草稿 #{draft_id}。",
                    title="已保存并退出",
                    border_style="yellow",
                )
            )
            raise typer.Exit() from None
        except ClarifierError as exc:
            self.console.print(f"[red]目标拆解失败：{exc}[/red]")
            raise typer.Exit(code=1) from exc
        except ValueError as exc:
            self.console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc
        except PlanGenerationError as exc:
            self.console.print(f"[red]计划生成失败：{exc}[/red]")
            raise typer.Exit(code=1) from exc

    def memory_show(
        self,
        recent_limit: Annotated[
            int,
            typer.Option("--recent-limit", "-n", help="显示最近多少条问答记录。"),
        ] = 8,
    ) -> None:
        """Show the local memory context injected into future LLM calls."""

        memory_context = self.state_manager.build_memory_context(recent_limit=recent_limit)
        self.console.print(
            Panel(
                Markdown(memory_context or "暂无长期记忆。先运行 `aura goal add` 完成几轮澄清。"),
                title=f"Aura 长期记忆 ({self.state_manager.db_path})",
                border_style="green",
            )
        )

    def plan_generate(
        self,
        session_id: Annotated[
            int | None,
            typer.Option("--session-id", "-s", help="使用指定澄清会话生成计划。"),
        ] = None,
        goal: Annotated[
            str | None,
            typer.Option("--goal", help="手动指定原始目标，需同时提供 --summary。"),
        ] = None,
        summary: Annotated[
            str | None,
            typer.Option("--summary", help="手动指定澄清摘要，需同时提供 --goal。"),
        ] = None,
        web: Annotated[
            bool,
            typer.Option("--web/--no-web", help="生成计划前是否联网检索学习资料。"),
        ] = True,
    ) -> None:
        """Generate a plan from an existing clarified profile."""

        settings = self.config_manager.load()
        if not settings.has_api_key:
            self.console.print("[red]DeepSeek API Key 尚未配置，请先运行 `aura config`。[/red]")
            raise typer.Exit(code=1)

        if bool(goal) != bool(summary):
            self.console.print("[red]--goal 和 --summary 必须同时提供。[/red]")
            raise typer.Exit(code=1)

        selected_session_id: int | None = None
        plan_goal = goal or ""
        plan_summary = summary or ""
        if not plan_goal:
            session = self.state_manager.get_clarification_session(session_id=session_id)
            if session is None:
                self.console.print("[red]没有找到可用于生成计划的澄清会话，请先运行 `aura goal add`。[/red]")
                raise typer.Exit(code=1)
            selected_session_id = session.id
            plan_goal = session.goal
            plan_summary = session.current_summary

        try:
            client = DeepSeekClientFactory(settings).create()
            memory_context = self.state_manager.build_memory_context()
            generated_plan = self._generate_plan(
                client=client,
                model=settings.model,
                session_id=selected_session_id,
                goal=plan_goal,
                summary=plan_summary,
                memory_context=memory_context,
                web=web,
            )
            self._render_generated_plan(generated_plan)
        except (ValueError, PlanGenerationError) as exc:
            self.console.print(f"[red]计划生成失败：{exc}[/red]")
            raise typer.Exit(code=1) from exc

    def plan_metadata(
        self,
        plan_id: Annotated[
            int,
            typer.Option("--plan-id", "-p", help="要修改元数据的计划 ID。"),
        ],
        category: Annotated[
            str | None,
            typer.Option("--category", "-c", help="计划分类，例如 red-team / math / language。"),
        ] = None,
        priority: Annotated[
            int | None,
            typer.Option("--priority", help="执行优先级：1 最高，5 最低。"),
        ] = None,
        importance: Annotated[
            int | None,
            typer.Option("--importance", help="长期重要性：1 最低，5 最高。"),
        ] = None,
    ) -> None:
        """Update category, priority, and importance for a plan."""

        self._validate_score("priority", priority)
        self._validate_score("importance", importance)
        try:
            self.state_manager.update_plan_metadata(
                plan_id=plan_id,
                category=category,
                priority=priority,
                importance=importance,
            )
        except ValueError as exc:
            self.console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc

        self._sync_plan_to_obsidian(plan_id)
        plan = self.state_manager.get_learning_plan(plan_id)
        self.console.print(
            Panel.fit(
                f"分类: {plan.category if plan else category}\n"
                f"优先级: {plan.priority if plan else priority}\n"
                f"重要性: {plan.importance if plan else importance}",
                title=f"计划 #{plan_id} 元数据已更新",
                border_style="green",
            )
        )

    def obsidian_config(
        self,
        vault: Annotated[
            str | None,
            typer.Option("--vault", "-v", help="Obsidian vault 路径。"),
        ] = None,
        folder: Annotated[
            str,
            typer.Option("--folder", "-f", help="Aura 在 vault 内使用的目录。"),
        ] = "VisionCraft",
    ) -> None:
        """Configure the Obsidian vault used for plan exports."""

        vault_path = vault or self.terminal_input.ask("请输入 Obsidian vault 路径")
        settings = self.config_manager.update_obsidian(vault_path=vault_path, folder=folder)
        self.console.print(
            Panel.fit(
                f"Vault: {settings.obsidian_vault_path}\nFolder: {settings.obsidian_folder}",
                title="Obsidian 配置已保存",
                border_style="green",
            )
        )

    def obsidian_sync(self) -> None:
        """Export all stored plans to Obsidian and rebuild the index."""

        plans = self.state_manager.list_learning_plans()
        if not plans:
            self.console.print("[yellow]暂无可同步的学习计划。[/yellow]")
            return

        exporter = self._build_obsidian_exporter()
        if exporter is None:
            self.console.print("[red]Obsidian vault 尚未配置，请先运行 `aura obsidian config --vault <path>`。[/red]")
            raise typer.Exit(code=1)

        results = exporter.export_all(plans)
        self.console.print(
            Panel.fit(
                f"已同步 {len(results)} 个计划。\n索引页: {exporter.index_path}",
                title="Obsidian 同步完成",
                border_style="green",
            )
        )

    def daily(
        self,
        plan_id: Annotated[
            int | None,
            typer.Option("--plan-id", "-p", help="指定要打卡的计划 ID。默认使用最新 active 计划。"),
        ] = None,
        no_adjust: Annotated[
            bool,
            typer.Option("--no-adjust", help="只记录打卡，不让 AI 调整计划。"),
        ] = False,
    ) -> None:
        """Daily check-in and AI-powered plan adjustment."""

        plan = self.state_manager.get_learning_plan(plan_id=plan_id)
        if plan is None:
            self.console.print("[red]没有找到可打卡的学习计划，请先运行 `aura plan generate`。[/red]")
            raise typer.Exit(code=1)

        energy_level = self._ask_energy_level()
        missed_days = self.state_manager.get_missed_days(plan.id)
        current_sequence = self.state_manager.get_current_sequence(plan.id)
        task_pool = [
            SchedulerTask(
                task_id=task.id,
                title=task.title,
                sequence_day=task.sequence_day,
                energy_level=task.energy_level,
            )
            for task in self.state_manager.get_energy_matched_tasks(
                plan_id=plan.id,
                energy_level=energy_level,
                current_sequence=current_sequence,
            )
        ]
        if not task_pool:
            self.state_manager.create_tasks_from_plan_markdown(plan.id, plan.markdown)
            current_sequence = self.state_manager.get_current_sequence(plan.id)
            task_pool = [
                SchedulerTask(
                    task_id=task.id,
                    title=task.title,
                    sequence_day=task.sequence_day,
                    energy_level=task.energy_level,
                )
                for task in self.state_manager.get_energy_matched_tasks(
                    plan_id=plan.id,
                    energy_level=energy_level,
                    current_sequence=current_sequence,
                )
            ]
        decision = self._schedule_today(
            missed_days=missed_days,
            current_sequence=current_sequence,
            energy_level=energy_level,
            task_pool=task_pool,
        )

        self.console.print(
            Panel.fit(
                f"计划 #{plan.id}: {plan.title}\n文件路径: {plan.output_path}",
                title="今日打卡",
                border_style="cyan",
            )
        )
        self.console.print(
            Panel(
                Markdown(self._scheduler_decision_to_markdown(decision)),
                title="今日柔性安排",
                border_style="blue",
            )
        )

        checkin = self._collect_daily_checkin(energy_level=energy_level)
        checkin_id = self.state_manager.save_daily_checkin(
            plan_id=plan.id,
            completed=checkin.completed,
            time_spent=checkin.time_spent,
            progress=checkin.progress,
            blockers=checkin.blockers,
            energy=checkin.energy,
            notes=checkin.notes,
        )
        self.state_manager.update_learning_habits(completed=checkin.completed)
        self.console.print(
            Panel.fit(
                f"今日打卡已保存为 #{checkin_id}。",
                title="记录完成",
                border_style="green",
            )
        )

        if no_adjust:
            return

        settings = self.config_manager.load()
        if not settings.has_api_key:
            self.console.print("[yellow]DeepSeek API Key 未配置，已跳过 AI 计划调整。[/yellow]")
            return

        try:
            client = DeepSeekClientFactory(settings).create()
            adjusted_plan = self._adjust_plan(
                client=client,
                model=settings.model,
                plan_id=plan.id,
                plan_title=plan.title,
                plan_markdown=plan.markdown,
                checkin=checkin,
            )
            self._render_adjusted_plan(adjusted_plan)
        except (ValueError, TrackerError) as exc:
            self.console.print(f"[red]计划调整失败：{exc}[/red]")
            raise typer.Exit(code=1) from exc

    def tree(
        self,
        plan_id: Annotated[
            int | None,
            typer.Option("--plan-id", "-p", help="指定计划 ID。默认使用最新 active 计划。"),
        ] = None,
        regenerate: Annotated[
            bool,
            typer.Option("--regenerate", help="忽略已存技能树，重新调用 LLM 生成。"),
        ] = False,
    ) -> None:
        """Render the current plan as a game-like skill tree."""

        plan = self.state_manager.get_learning_plan(plan_id=plan_id)
        if plan is None:
            self.console.print("[red]没有找到可展示的学习计划，请先运行 `aura plan generate`。[/red]")
            raise typer.Exit(code=1)

        topology_json = None if regenerate else self.state_manager.get_skill_tree(plan.id)
        if topology_json is None:
            settings = self.config_manager.load()
            if not settings.has_api_key:
                self.console.print("[red]当前计划还没有目标拓扑，且 DeepSeek API Key 未配置，无法生成。[/red]")
                raise typer.Exit(code=1)
            try:
                client = DeepSeekClientFactory(settings).create()
                with self.console.status("[bold cyan]Aura 正在生成目标拓扑...[/bold cyan]", spinner="dots"):
                    topology = TopologyGenerator(client=client, model=settings.model).generate(
                        goal=plan.goal,
                        plan_markdown=plan.markdown,
                    )
                topology_json = topology.to_json()
                self.state_manager.save_skill_tree(plan.id, topology_json)
            except (ValueError, TopologyError) as exc:
                self.console.print(f"[red]目标拓扑生成失败：{exc}[/red]")
                raise typer.Exit(code=1) from exc
        else:
            topology = parse_topology(topology_json)

        TopologyRenderer(self.console).render(topology)

    def _render_clarification_result(
        self,
        result: ClarificationResult,
        debug: bool,
    ) -> None:
        self.console.print(
            Panel(
                Markdown(result.current_summary or "暂无摘要。"),
                title="当前目标摘要",
                border_style="blue",
            )
        )
        if debug:
            self.console.print(
                Panel(
                    result.thought_process or "无内部判断。",
                    title="Clarifier Debug",
                    border_style="magenta",
                )
            )

    def _render_next_question(self, question: str, question_index: int) -> None:
        self.console.print(
            Panel(
                question,
                title=f"问题 {question_index}",
                border_style="cyan",
            )
        )

    def _render_ready_summary(self, summary: str) -> None:
        self.console.print(
            Panel(
                Markdown(summary or "信息已足够清晰。"),
                title="信息收集完毕，准备生成计划",
                border_style="green",
            )
        )

    def _request_clarification(
        self,
        clarifier: ClarificationAgent,
        messages: list[ChatMessage],
    ) -> ClarificationResult:
        with self.console.status("[bold cyan]Aura 正在思考...[/bold cyan]", spinner="dots"):
            return clarifier.evaluate_messages(messages)

    def _generate_plan(
        self,
        client: OpenAI,
        model: str,
        session_id: int | None,
        goal: str,
        summary: str,
        memory_context: str,
        web: bool,
    ) -> GeneratedPlan:
        learning_habits = self.state_manager.build_learning_habits_context()
        resources_context = self._research_resources(goal=goal, summary=summary) if web else ""
        plan_generator = PlanGenerator(client=client, model=model)
        with self.console.status("[bold green]Aura 正在生成学习计划...[/bold green]", spinner="dots"):
            generated_plan = plan_generator.generate(
                goal=goal,
                clarified_summary=summary,
                memory_context=memory_context,
                learning_habits=learning_habits,
                resources_context=resources_context,
            )

        plan_id = self.state_manager.save_learning_plan(
            session_id=session_id,
            goal=goal,
            title=generated_plan.title,
            summary=summary,
            markdown=generated_plan.markdown,
            output_path=generated_plan.output_path,
        )
        self.state_manager.create_tasks_from_plan_markdown(plan_id, generated_plan.markdown)
        self._ensure_skill_tree(
            plan_id=plan_id,
            markdown=generated_plan.markdown,
            client=client,
            model=model,
            goal=goal,
        )
        if session_id is not None:
            self.state_manager.update_clarification_session(
                session_id=session_id,
                current_summary=summary,
                status="planned",
            )
        self.console.print(
            Panel.fit(
                f"计划已保存为 #{plan_id}\n文件路径: {generated_plan.output_path}",
                title="学习计划已生成",
                border_style="green",
            )
        )
        self._sync_plan_to_obsidian(plan_id)
        return generated_plan

    def _research_resources(self, goal: str, summary: str) -> str:
        try:
            with self.console.status("[bold cyan]Aura 正在搜索学习资料...[/bold cyan]", spinner="dots"):
                bundle = ResourceResearcher().research(goal=goal, summary=summary)
        except Exception as exc:
            return f"资料检索失败：{exc}"

        return bundle.to_markdown_context()

    def _ensure_skill_tree(
        self,
        plan_id: int,
        markdown: str,
        client: OpenAI,
        model: str,
        goal: str = "",
    ) -> None:
        if self.state_manager.get_skill_tree(plan_id) is not None:
            return
        try:
            topology = TopologyGenerator(client=client, model=model).generate(
                goal=goal,
                plan_markdown=markdown,
            )
            self.state_manager.save_skill_tree(plan_id, topology.to_json())
        except TopologyError:
            return

    def _ask_energy_level(self) -> int:
        value = IntPrompt.ask(
            "你今天感觉精力如何？[1(疲惫)-5(专注)]",
            choices=["1", "2", "3", "4", "5"],
            default=3,
        )
        return int(value)

    def _collect_daily_checkin(self, energy_level: int) -> CheckInReport:
        completed_text = self.terminal_input.ask("今天是否完成计划任务？(y/n)")
        completed = completed_text.strip().lower() in {"y", "yes", "是", "完成", "done"}
        return CheckInReport(
            completed=completed,
            time_spent=self.terminal_input.ask("今天学习了多久？例如 2h / 45min"),
            progress=self.terminal_input.ask("今天具体完成了什么？"),
            blockers=self.terminal_input.ask("遇到哪些卡点或阻碍？没有可填 无"),
            energy=str(energy_level),
            notes=self.terminal_input.ask("还有什么需要 Aura 记住？没有可填 无"),
        )

    def _schedule_today(
        self,
        missed_days: int,
        current_sequence: int,
        energy_level: int,
        task_pool: list[SchedulerTask],
    ):
        settings = self.config_manager.load()
        scheduler: HumanCentricScheduler
        if settings.has_api_key:
            try:
                client = DeepSeekClientFactory(settings).create()
                scheduler = HumanCentricScheduler(client=client, model=settings.model)
                return scheduler.reschedule(
                    missed_days=missed_days,
                    current_sequence=current_sequence,
                    energy_level=energy_level,
                    task_pool=task_pool,
                )
            except (ValueError, SchedulerError):
                pass

        return HumanCentricScheduler.fallback_decision(
            missed_days=missed_days,
            current_sequence=current_sequence,
            energy_level=energy_level,
            task_pool=task_pool,
        )

    def _scheduler_decision_to_markdown(self, decision) -> str:
        from aura.agents.daily_tracker import decision_to_markdown

        return decision_to_markdown(decision)

    def _adjust_plan(
        self,
        client: OpenAI,
        model: str,
        plan_id: int,
        plan_title: str,
        plan_markdown: str,
        checkin: CheckInReport,
    ) -> AdjustedPlan:
        recent_checkins = self.state_manager.get_recent_checkins(plan_id=plan_id)
        recent_context = self._format_recent_checkins(recent_checkins)
        learning_habits = self.state_manager.build_learning_habits_context()
        memory_context = self.state_manager.build_memory_context()
        tracker = DailyTracker(client=client, model=model)
        with self.console.status("[bold green]Aura 正在调整后续计划...[/bold green]", spinner="dots"):
            adjusted_plan = tracker.adjust_plan(
                plan_title=plan_title,
                plan_markdown=plan_markdown,
                checkin=checkin,
                recent_checkins_context=recent_context,
                learning_habits=learning_habits,
                memory_context=memory_context,
            )

        new_plan_id = self.state_manager.replace_active_plan(
            old_plan_id=plan_id,
            title=adjusted_plan.title,
            markdown=adjusted_plan.markdown,
            output_path=adjusted_plan.output_path,
        )
        self.state_manager.create_tasks_from_plan_markdown(new_plan_id, adjusted_plan.markdown)
        self._ensure_skill_tree(
            plan_id=new_plan_id,
            markdown=adjusted_plan.markdown,
            client=client,
            model=model,
            goal=plan_title,
        )
        self.console.print(
            Panel.fit(
                f"调整后的计划已保存为 #{new_plan_id}\n文件路径: {adjusted_plan.output_path}",
                title="计划已更新",
                border_style="green",
            )
        )
        self._sync_plan_to_obsidian(new_plan_id)
        return adjusted_plan

    def _format_recent_checkins(self, checkins: object) -> str:
        lines: list[str] = []
        for checkin in checkins:
            completed = "完成" if checkin.completed else "未完成"
            lines.append(
                f"- {checkin.checkin_date}: {completed}；时长：{checkin.time_spent or '未填'}；"
                f"进展：{checkin.progress or '未填'}；阻碍：{checkin.blockers or '无'}；"
                f"精力：{checkin.energy or '未填'}；备注：{checkin.notes or '无'}"
            )
        return "\n".join(lines)

    def _render_adjusted_plan(self, adjusted_plan: AdjustedPlan) -> None:
        self.console.print(
            Panel(
                Markdown(adjusted_plan.markdown),
                title=adjusted_plan.title,
                border_style="green",
            )
        )

    def _build_obsidian_exporter(self) -> ObsidianExporter | None:
        settings = self.config_manager.load()
        if not settings.obsidian_vault_path.strip():
            return None
        return ObsidianExporter(
            vault_path=Path(settings.obsidian_vault_path),
            folder=settings.obsidian_folder,
        )

    def _sync_plan_to_obsidian(self, plan_id: int) -> None:
        exporter = self._build_obsidian_exporter()
        if exporter is None:
            return

        plan = self.state_manager.get_learning_plan(plan_id)
        if plan is None:
            return

        try:
            result = exporter.export_plan(plan, self.state_manager.list_learning_plans())
        except ValueError as exc:
            self.console.print(f"[yellow]Obsidian 同步跳过：{exc}[/yellow]")
            return

        self.console.print(
            Panel.fit(
                f"计划笔记: {result.note_path}\n索引页: {result.index_path}",
                title="已同步到 Obsidian",
                border_style="blue",
            )
        )

    def _render_generated_plan(self, generated_plan: GeneratedPlan) -> None:
        self.console.print(
            Panel(
                Markdown(generated_plan.markdown),
                title=generated_plan.title,
                border_style="green",
            )
        )

    def _is_exit_command(self, value: str) -> bool:
        return value.strip().lower() in {"exit", "quit"}

    def _validate_score(self, name: str, value: int | None) -> None:
        if value is not None and not 1 <= value <= 5:
            self.console.print(f"[red]{name} 必须在 1 到 5 之间。[/red]")
            raise typer.Exit(code=1)

    def _save_goal_draft(
        self,
        goal: str,
        messages: list[ChatMessage],
        current_summary: str,
        status: str,
    ) -> int:
        return self.state_manager.save_clarification_draft(
            goal=goal,
            messages=messages,
            current_summary=current_summary,
            status=status,
        )


cli = AuraCLI()
app = cli.app


if __name__ == "__main__":
    app()
