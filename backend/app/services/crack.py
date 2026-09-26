"""裂缝处置业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "crack"
REQUIRED_FIELDS = ["处置单号", "所在路段", "裂缝类型"]
OPTIONAL_FIELDS = ["裂缝长度", "灌缝材料", "作业班组", "完成日期"]
STATUS_ORDER = ["待安排", "处置中", "已完成", "已取消"]
TERMINAL_STATUSES = {"已完成", "已取消"}
DISPLAY_STATUS_FIELD = "处置状态"
ACTION_RULES = {"安排处置": "处置中", "确认完成": "已完成", "取消处置": "已取消"}
NEGATIVE_ACTIONS = []


class CrackService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        section: str | None = None,
        crack_type: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("处置单号", ""))]
        if section:
            rows = [row for row in rows if section in str(row.get("所在路段", ""))]
        if crack_type:
            rows = [row for row in rows if crack_type in str(row.get("裂缝类型", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def summary(self) -> dict[str, Any]:
        """统计卡片：待安排只数在途单，已完成/已取消不计入；与列表同源，刷新后一致。"""
        rows = store.rows(MODULE)
        month = date.today().strftime("%Y-%m")
        pending = sum(1 for row in rows if row.get("status") == STATUS_ORDER[0])
        cancelled = sum(1 for row in rows if row.get("status") == STATUS_ORDER[-1])
        month_length = 0.0
        for row in rows:
            if row.get("status") != "已完成":
                continue
            if not str(row.get("完成日期") or "").startswith(month):
                continue
            try:
                month_length += float(row.get("裂缝长度") or 0)
            except (TypeError, ValueError):
                continue
        length_value: float | int = (
            int(month_length) if month_length == int(month_length) else round(month_length, 2)
        )
        return {"cards": [
            {"label": "待安排处置", "value": pending},
            {"label": "本月处置长度", "value": length_value},
            {"label": "取消单数", "value": cancelled},
        ]}

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            value = values.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            entry[field] = value.strip() if isinstance(value, str) else value
        entry["status"] = STATUS_ORDER[0]
        entry[DISPLAY_STATUS_FIELD] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"处置单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于裂缝处置可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry[DISPLAY_STATUS_FIELD] = target
        entry["pending"] = target not in TERMINAL_STATUSES
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"处置单已{action}"
