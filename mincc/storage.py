"""本地持久化存储。

用户级运行数据统一放在 ~/.mincc 下，并按 project 与数据类型归档。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePath

MINCC_HOME = ".mincc"
INPUT_HISTORY_TYPE = "input_history"
MAX_PROJECT_ID_LENGTH = 200


def _slug_part(text: str) -> str:
    return re.sub(r"[^\w_.-]+", "-", text, flags=re.UNICODE).strip("-")


def project_id_from_path(path: PurePath) -> str:
    """根据项目路径生成稳定的项目 ID。"""
    resolved = path.resolve() if isinstance(path, Path) else path
    parts = list(resolved.parts)

    if resolved.anchor and parts and parts[0] == resolved.anchor:
        parts = parts[1:]
        anchor = resolved.drive or resolved.anchor.strip("/\\")
        if anchor:
            parts.insert(0, anchor)

    project_id = "-".join(part for part in (_slug_part(p) for p in parts) if part)
    project_id = project_id or "project"
    if len(project_id) > MAX_PROJECT_ID_LENGTH:
        project_id = project_id[-MAX_PROJECT_ID_LENGTH:].strip("-_.") or "project"
    return project_id


@dataclass(frozen=True)
class MinccStorage:
    root: Path
    project_id: str

    @classmethod
    def create(
        cls,
        root: Path | None = None,
        project_id: str | None = None,
        project_path: Path | None = None,
    ) -> MinccStorage:
        return cls(
            root=root or Path.home() / MINCC_HOME,
            project_id=project_id or project_id_from_path(project_path or Path.cwd()),
        )

    @property
    def project_dir(self) -> Path:
        return self.root / "projects" / self.project_id

    def records_path(self, data_type: str) -> Path:
        return self.project_dir / data_type / "records.jsonl"

    def append_record(self, data_type: str, payload: dict) -> None:
        path = self.records_path(data_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            **payload,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def append_input(self, text: str) -> None:
        self.append_record(INPUT_HISTORY_TYPE, {"text": text})

    def read_inputs(self) -> list[str]:
        path = self.records_path(INPUT_HISTORY_TYPE)
        if not path.exists():
            return []

        out: list[str] = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = record.get("text")
                if isinstance(text, str) and text:
                    out.append(text)
        return out
