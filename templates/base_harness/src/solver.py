from __future__ import annotations

from typing import Any


class BaselineSolver:
    """MVP baseline solver.

    This intentionally does not optimize score. It only proves the harness path:
    load tasks → predict → verify → write submission.
    """

    def __init__(self, default_answer: str = "1") -> None:
        self.default_answer = default_answer

    def solve_one(self, task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        output = config.get("output", {})
        id_col = output.get("id_column", "id")
        target_col = output.get("target_column", "answer")
        return {
            id_col: task.get(id_col, task.get("id", "")),
            target_col: self.default_answer,
        }

    def solve_all(self, tasks: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
        return [self.solve_one(task, config) for task in tasks]
