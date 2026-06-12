"""SQLite-backed state manager placeholder for learning behavior data."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TypeAlias

ChatMessage: TypeAlias = dict[str, str]


@dataclass(frozen=True, slots=True)
class StoredClarificationSession:
    """A clarified goal session that can be used as plan input."""

    id: int
    goal: str
    current_summary: str
    status: str


@dataclass(frozen=True, slots=True)
class StoredClarificationDraft:
    """A saved clarification conversation that can be resumed."""

    id: int
    goal: str
    messages: list[ChatMessage]
    current_summary: str
    status: str


@dataclass(frozen=True, slots=True)
class StoredLearningPlan:
    """A persisted learning plan."""

    id: int
    session_id: int | None
    goal: str
    title: str
    summary: str
    markdown: str
    output_path: Path
    status: str
    category: str
    priority: int
    importance: int


@dataclass(frozen=True, slots=True)
class StoredDailyCheckIn:
    """A persisted daily progress record."""

    id: int
    plan_id: int
    checkin_date: str
    completed: bool
    time_spent: str
    progress: str
    blockers: str
    energy: str
    notes: str


@dataclass(frozen=True, slots=True)
class StoredLearningTask:
    """A sequence-based learning task without a hard due date."""

    id: int
    plan_id: int
    sequence_day: int
    title: str
    energy_level: int
    status: str
    node_id: str


class StateManager:
    """Owns local state such as goals, daily check-ins, and learning habits."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or Path.home() / ".local" / "share" / "visioncraft" / "aura.db"

    def reset(self, reinitialize: bool = True) -> None:
        """Delete all persisted Aura state and optionally recreate empty tables."""

        if self.db_path.exists():
            self.db_path.unlink()
        if reinitialize:
            self.initialize()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_habits (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    missed_days INTEGER NOT NULL DEFAULT 0,
                    completed_days INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO learning_habits (id)
                VALUES (1)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS clarification_drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal TEXT NOT NULL,
                    messages_json TEXT NOT NULL,
                    current_summary TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'interrupted',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS clarification_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    current_summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS question_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    goal TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES clarification_sessions (id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_profile (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    profile_summary TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO user_profile (id)
                VALUES (1)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    goal TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    markdown TEXT NOT NULL,
                    output_path TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    category TEXT NOT NULL DEFAULT 'general',
                    priority INTEGER NOT NULL DEFAULT 3,
                    importance INTEGER NOT NULL DEFAULT 3,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES clarification_sessions (id)
                )
                """
            )
            self._ensure_learning_plan_columns(connection)
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_checkins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id INTEGER NOT NULL,
                    checkin_date TEXT NOT NULL DEFAULT CURRENT_DATE,
                    completed INTEGER NOT NULL DEFAULT 0,
                    time_spent TEXT NOT NULL DEFAULT '',
                    progress TEXT NOT NULL DEFAULT '',
                    blockers TEXT NOT NULL DEFAULT '',
                    energy TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (plan_id) REFERENCES learning_plans (id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id INTEGER NOT NULL,
                    sequence_day INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    energy_level INTEGER NOT NULL DEFAULT 3,
                    status TEXT NOT NULL DEFAULT 'pending',
                    node_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (plan_id) REFERENCES learning_plans (id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_trees (
                    plan_id INTEGER PRIMARY KEY,
                    tree_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (plan_id) REFERENCES learning_plans (id)
                )
                """
            )

    def save_clarification_draft(
        self,
        goal: str,
        messages: list[ChatMessage],
        current_summary: str = "",
        status: str = "interrupted",
    ) -> int:
        """Persist an interrupted goal clarification conversation."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO clarification_drafts (
                    goal,
                    messages_json,
                    current_summary,
                    status
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    goal.strip(),
                    json.dumps(messages, ensure_ascii=False),
                    current_summary.strip(),
                    status,
                ),
            )
            return int(cursor.lastrowid)

    def get_clarification_draft(self, draft_id: int) -> StoredClarificationDraft | None:
        """Return a saved clarification draft by id."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT id, goal, messages_json, current_summary, status
                FROM clarification_drafts
                WHERE id = ?
                """,
                (draft_id,),
            ).fetchone()
        if not row:
            return None

        try:
            messages = json.loads(str(row[2]))
        except json.JSONDecodeError:
            messages = []

        return StoredClarificationDraft(
            id=int(row[0]),
            goal=str(row[1]),
            messages=messages,
            current_summary=str(row[3]),
            status=str(row[4]),
        )

    def update_clarification_draft(
        self,
        draft_id: int,
        messages: list[ChatMessage],
        current_summary: str,
        status: str,
    ) -> None:
        """Update a saved clarification draft after resume."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE clarification_drafts
                SET messages_json = ?,
                    current_summary = ?,
                    status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    json.dumps(messages, ensure_ascii=False),
                    current_summary.strip(),
                    status,
                    draft_id,
                ),
            )

    def create_tasks_from_plan_markdown(self, plan_id: int, markdown: str) -> None:
        """Extract sequence tasks from plan Markdown and store them without due dates."""

        tasks = self._extract_tasks(markdown)
        if not tasks:
            tasks = [
                {
                    "sequence_day": 1,
                    "title": "回顾当前计划并完成 10 分钟启动任务",
                    "energy_level": 1,
                    "node_id": "",
                }
            ]
        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("DELETE FROM learning_tasks WHERE plan_id = ?", (plan_id,))
            connection.executemany(
                """
                INSERT INTO learning_tasks (plan_id, sequence_day, title, energy_level, node_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        plan_id,
                        task["sequence_day"],
                        task["title"],
                        task["energy_level"],
                        task["node_id"],
                    )
                    for task in tasks
                ],
            )

    def create_clarification_session(self, goal: str) -> int:
        """Start tracking a goal clarification session."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO clarification_sessions (goal)
                VALUES (?)
                """,
                (goal.strip(),),
            )
            return int(cursor.lastrowid)

    def record_question_answer(
        self,
        session_id: int,
        goal: str,
        question: str,
        answer: str,
    ) -> int:
        """Persist one clarification question and the user's answer."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO question_records (
                    session_id,
                    goal,
                    question,
                    answer
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    session_id,
                    goal.strip(),
                    question.strip(),
                    answer.strip(),
                ),
            )
            return int(cursor.lastrowid)

    def update_clarification_session(
        self,
        session_id: int,
        current_summary: str,
        status: str,
    ) -> None:
        """Update the current session summary and lifecycle status."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE clarification_sessions
                SET current_summary = ?,
                    status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (current_summary.strip(), status, session_id),
            )

    def update_user_profile_from_summary(self, summary: str) -> None:
        """Fold a completed clarification summary into the long-term profile."""

        clean_summary = summary.strip()
        if not clean_summary:
            return

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT profile_summary
                FROM user_profile
                WHERE id = 1
                """
            ).fetchone()
            existing_summary = str(row[0]) if row and row[0] else ""
            if clean_summary in existing_summary:
                return

            profile_summary = self._append_profile_entry(existing_summary, clean_summary)
            connection.execute(
                """
                UPDATE user_profile
                SET profile_summary = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
                """,
                (profile_summary,),
            )

    def build_memory_context(self, recent_limit: int = 8) -> str:
        """Build a compact memory block to inject into future LLM calls."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            profile_row = connection.execute(
                """
                SELECT profile_summary
                FROM user_profile
                WHERE id = 1
                """
            ).fetchone()
            record_rows = connection.execute(
                """
                SELECT goal, question, answer
                FROM question_records
                ORDER BY id DESC
                LIMIT ?
                """,
                (recent_limit,),
            ).fetchall()

        profile_summary = str(profile_row[0]).strip() if profile_row and profile_row[0] else ""
        recent_records = [
            f"- 目标：{goal}\n  问：{question}\n  答：{answer}"
            for goal, question, answer in reversed(record_rows)
        ]

        parts: list[str] = []
        if profile_summary:
            parts.append(f"用户长期画像：\n{profile_summary}")
        if recent_records:
            parts.append("最近澄清记录：\n" + "\n".join(recent_records))
        return "\n\n".join(parts)

    def build_learning_habits_context(self) -> str:
        """Build a short learning-habits summary for plan difficulty tuning."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT missed_days, completed_days, updated_at
                FROM learning_habits
                WHERE id = 1
                """
            ).fetchone()

        if not row:
            return "暂无学习习惯记录。"

        missed_days, completed_days, updated_at = row
        if missed_days and int(missed_days) >= 3:
            recommendation = "用户近期可能存在连续中断，计划应降低每日负担，并优先安排低摩擦启动任务。"
        elif completed_days and int(completed_days) >= 5:
            recommendation = "用户近期执行稳定，可以安排适度挑战性的阶段产出。"
        else:
            recommendation = "习惯数据不足，计划应从稳健节奏开始。"

        return (
            f"连续未完成天数：{missed_days}\n"
            f"累计完成天数：{completed_days}\n"
            f"更新时间：{updated_at}\n"
            f"难度建议：{recommendation}"
        )

    def save_learning_plan(
        self,
        session_id: int | None,
        goal: str,
        title: str,
        summary: str,
        markdown: str,
        output_path: Path,
        status: str = "active",
        category: str = "general",
        priority: int = 3,
        importance: int = 3,
    ) -> int:
        """Persist a generated learning plan."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO learning_plans (
                    session_id,
                    goal,
                    title,
                    summary,
                    markdown,
                    output_path,
                    status,
                    category,
                    priority,
                    importance
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    goal.strip(),
                    title.strip(),
                    summary.strip(),
                    markdown.strip(),
                    str(output_path),
                    status,
                    category.strip() or "general",
                    priority,
                    importance,
                ),
            )
            return int(cursor.lastrowid)

    def get_learning_plan(self, plan_id: int | None = None) -> StoredLearningPlan | None:
        """Return a specific or latest active learning plan."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            if plan_id is not None:
                row = connection.execute(
                    """
                    SELECT id, session_id, goal, title, summary, markdown, output_path, status, category, priority, importance
                    FROM learning_plans
                    WHERE id = ?
                    """,
                    (plan_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT id, session_id, goal, title, summary, markdown, output_path, status, category, priority, importance
                    FROM learning_plans
                    WHERE status = 'active'
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                    """
                ).fetchone()

        if not row:
            return None

        return StoredLearningPlan(
            id=int(row[0]),
            session_id=int(row[1]) if row[1] is not None else None,
            goal=str(row[2]),
            title=str(row[3]),
            summary=str(row[4]),
            markdown=str(row[5]),
            output_path=Path(str(row[6])),
            status=str(row[7]),
            category=str(row[8]),
            priority=int(row[9]),
            importance=int(row[10]),
        )

    def list_learning_plans(self) -> list[StoredLearningPlan]:
        """Return all learning plans for Obsidian export and management."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, goal, title, summary, markdown, output_path, status, category, priority, importance
                FROM learning_plans
                ORDER BY importance DESC, priority ASC, updated_at DESC, id DESC
                """
            ).fetchall()

        return [
            StoredLearningPlan(
                id=int(row[0]),
                session_id=int(row[1]) if row[1] is not None else None,
                goal=str(row[2]),
                title=str(row[3]),
                summary=str(row[4]),
                markdown=str(row[5]),
                output_path=Path(str(row[6])),
                status=str(row[7]),
                category=str(row[8]),
                priority=int(row[9]),
                importance=int(row[10]),
            )
            for row in rows
        ]

    def update_plan_metadata(
        self,
        plan_id: int,
        category: str | None = None,
        priority: int | None = None,
        importance: int | None = None,
    ) -> None:
        """Update category, priority, or importance for one plan."""

        current = self.get_learning_plan(plan_id)
        if current is None:
            raise ValueError(f"计划 #{plan_id} 不存在。")

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE learning_plans
                SET category = ?,
                    priority = ?,
                    importance = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    (category.strip() if category else current.category) or "general",
                    priority if priority is not None else current.priority,
                    importance if importance is not None else current.importance,
                    plan_id,
                ),
            )

    def save_daily_checkin(
        self,
        plan_id: int,
        completed: bool,
        time_spent: str,
        progress: str,
        blockers: str,
        energy: str,
        notes: str,
    ) -> int:
        """Persist one daily check-in."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO daily_checkins (
                    plan_id,
                    checkin_date,
                    completed,
                    time_spent,
                    progress,
                    blockers,
                    energy,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_id,
                    date.today().isoformat(),
                    1 if completed else 0,
                    time_spent.strip(),
                    progress.strip(),
                    blockers.strip(),
                    energy.strip(),
                    notes.strip(),
                ),
            )
            return int(cursor.lastrowid)

    def update_learning_habits(self, completed: bool) -> None:
        """Update coarse habit counters from a daily check-in."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            if completed:
                connection.execute(
                    """
                    UPDATE learning_habits
                    SET completed_days = completed_days + 1,
                        missed_days = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                    """
                )
            else:
                connection.execute(
                    """
                    UPDATE learning_habits
                    SET missed_days = missed_days + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                    """
                )

    def get_recent_checkins(
        self,
        plan_id: int,
        limit: int = 7,
    ) -> list[StoredDailyCheckIn]:
        """Return recent check-ins for the same learning goal across plan versions."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    daily_checkins.id,
                    daily_checkins.plan_id,
                    daily_checkins.checkin_date,
                    daily_checkins.completed,
                    daily_checkins.time_spent,
                    daily_checkins.progress,
                    daily_checkins.blockers,
                    daily_checkins.energy,
                    daily_checkins.notes
                FROM daily_checkins
                JOIN learning_plans ON daily_checkins.plan_id = learning_plans.id
                WHERE learning_plans.goal = (
                    SELECT goal
                    FROM learning_plans
                    WHERE id = ?
                )
                ORDER BY daily_checkins.checkin_date DESC, daily_checkins.id DESC
                LIMIT ?
                """,
                (plan_id, limit),
            ).fetchall()

        return [
            StoredDailyCheckIn(
                id=int(row[0]),
                plan_id=int(row[1]),
                checkin_date=str(row[2]),
                completed=bool(row[3]),
                time_spent=str(row[4]),
                progress=str(row[5]),
                blockers=str(row[6]),
                energy=str(row[7]),
                notes=str(row[8]),
            )
            for row in reversed(rows)
        ]

    def get_missed_days(self, plan_id: int) -> int:
        """Return silent gap days since the latest check-in, never as overdue."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT MAX(checkin_date)
                FROM daily_checkins
                WHERE plan_id IN (
                    SELECT id
                    FROM learning_plans
                    WHERE goal = (
                        SELECT goal
                        FROM learning_plans
                        WHERE id = ?
                    )
                )
                """,
                (plan_id,),
            ).fetchone()
        if not row or not row[0]:
            return 0
        latest = datetime.strptime(str(row[0]), "%Y-%m-%d").date()
        return max((date.today() - latest).days - 1, 0)

    def get_current_sequence(self, plan_id: int) -> int:
        """Return the next unfinished sequence day."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT MIN(sequence_day)
                FROM learning_tasks
                WHERE plan_id = ?
                  AND status != 'completed'
                """,
                (plan_id,),
            ).fetchone()
        return int(row[0]) if row and row[0] is not None else 1

    def get_energy_matched_tasks(
        self,
        plan_id: int,
        energy_level: int,
        current_sequence: int,
        limit: int = 8,
    ) -> list[StoredLearningTask]:
        """Return tasks at or below the user's energy threshold."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT id, plan_id, sequence_day, title, energy_level, status, node_id
                FROM learning_tasks
                WHERE plan_id = ?
                  AND sequence_day >= ?
                  AND energy_level <= ?
                  AND status != 'completed'
                ORDER BY sequence_day ASC, energy_level ASC, id ASC
                LIMIT ?
                """,
                (plan_id, current_sequence, energy_level, limit),
            ).fetchall()

        return [
            StoredLearningTask(
                id=int(row[0]),
                plan_id=int(row[1]),
                sequence_day=int(row[2]),
                title=str(row[3]),
                energy_level=int(row[4]),
                status=str(row[5]),
                node_id=str(row[6]),
            )
            for row in rows
        ]

    def save_skill_tree(self, plan_id: int, tree_json: str) -> None:
        """Persist a skill tree DAG JSON blob for a plan."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO skill_trees (plan_id, tree_json)
                VALUES (?, ?)
                ON CONFLICT(plan_id) DO UPDATE SET
                    tree_json = excluded.tree_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (plan_id, tree_json),
            )

    def get_skill_tree(self, plan_id: int) -> str | None:
        """Return stored skill tree JSON for a plan."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT tree_json
                FROM skill_trees
                WHERE plan_id = ?
                """,
                (plan_id,),
            ).fetchone()
        return str(row[0]) if row and row[0] else None

    def replace_active_plan(
        self,
        old_plan_id: int,
        title: str,
        markdown: str,
        output_path: Path,
    ) -> int:
        """Mark the old plan adjusted and insert a new active plan version."""

        old_plan = self.get_learning_plan(old_plan_id)
        if old_plan is None:
            raise ValueError(f"计划 #{old_plan_id} 不存在。")

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE learning_plans
                SET status = 'adjusted',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (old_plan_id,),
            )
            cursor = connection.execute(
                """
                INSERT INTO learning_plans (
                    session_id,
                    goal,
                    title,
                    summary,
                    markdown,
                    output_path,
                    status,
                    category,
                    priority,
                    importance
                )
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    old_plan.session_id,
                    old_plan.goal,
                    title.strip(),
                    old_plan.summary,
                    markdown.strip(),
                    str(output_path),
                    old_plan.category,
                    old_plan.priority,
                    old_plan.importance,
                ),
            )
            return int(cursor.lastrowid)

    def get_clarification_session(
        self,
        session_id: int | None = None,
    ) -> StoredClarificationSession | None:
        """Return a specific or latest usable clarification session."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            if session_id is not None:
                row = connection.execute(
                    """
                    SELECT id, goal, current_summary, status
                    FROM clarification_sessions
                    WHERE id = ?
                    """,
                    (session_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT id, goal, current_summary, status
                    FROM clarification_sessions
                    WHERE current_summary != ''
                      AND status IN ('clarified', 'planned', 'active')
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                    """
                ).fetchone()

        if not row:
            return None

        return StoredClarificationSession(
            id=int(row[0]),
            goal=str(row[1]),
            current_summary=str(row[2]),
            status=str(row[3]),
        )

    def _append_profile_entry(self, existing_summary: str, new_summary: str) -> str:
        entries = [entry for entry in [existing_summary.strip(), f"- {new_summary}"] if entry]
        profile_summary = "\n".join(entries)
        max_length = 4000
        if len(profile_summary) <= max_length:
            return profile_summary
        return profile_summary[-max_length:]

    def _ensure_learning_plan_columns(self, connection: sqlite3.Connection) -> None:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(learning_plans)").fetchall()
        }
        migrations = {
            "category": "ALTER TABLE learning_plans ADD COLUMN category TEXT NOT NULL DEFAULT 'general'",
            "priority": "ALTER TABLE learning_plans ADD COLUMN priority INTEGER NOT NULL DEFAULT 3",
            "importance": "ALTER TABLE learning_plans ADD COLUMN importance INTEGER NOT NULL DEFAULT 3",
        }
        for column, statement in migrations.items():
            if column not in columns:
                connection.execute(statement)

    def _extract_tasks(self, markdown: str) -> list[dict[str, int | str]]:
        tasks: list[dict[str, int | str]] = []
        current_sequence = 1
        for line in markdown.splitlines():
            sequence_match = re.search(r"Sequence Day\s*(\d+)|sequence_day\s*[:：]\s*(\d+)", line, re.I)
            if sequence_match:
                current_sequence = int(next(group for group in sequence_match.groups() if group))

            energy_match = re.search(r"energy_level\s*[:：]\s*([1-5])", line, re.I)
            task_match = re.search(r"(?:^[-*]\s+\[[ xX]\]\s*|^[-*]\s+)(.+)", line)
            if not energy_match or not task_match:
                continue

            title = re.sub(r"energy_level\s*[:：]\s*[1-5]", "", task_match.group(1), flags=re.I)
            title = re.sub(r"sequence_day\s*[:：]\s*\d+", "", title, flags=re.I)
            title = title.strip(" |-")
            if not title:
                continue

            node_match = re.search(r"node_id\s*[:：]\s*([\w-]+)", line, re.I)
            tasks.append(
                {
                    "sequence_day": current_sequence,
                    "title": title,
                    "energy_level": int(energy_match.group(1)),
                    "node_id": node_match.group(1) if node_match else "",
                }
            )
        return tasks
