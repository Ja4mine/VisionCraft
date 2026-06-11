"""Terminal input helpers with robust line editing."""

from __future__ import annotations

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.patch_stdout import patch_stdout


class TerminalInput:
    """Prompt users with reliable editing for CJK text in modern terminals."""

    def __init__(self) -> None:
        self._session: PromptSession[str] | None = None

    def ask(self, message: str, password: bool = False) -> str:
        """Read a single line while preserving backspace/delete behavior."""

        prompt = ANSI(f"\x1b[1m{message}\x1b[0m: ")
        with patch_stdout():
            return self.session.prompt(prompt, is_password=password)

    @property
    def session(self) -> PromptSession[str]:
        if self._session is None:
            self._session = PromptSession()
        return self._session
