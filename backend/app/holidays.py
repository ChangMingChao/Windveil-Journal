"""内置节假日数据源（holiday-aware-timing，架构 5.5）。

数据文件 `app/data/holidays_{year}.json` 随镜像发布：年份粒度、只读、无网络请求。
加载器按年份懒加载 + 进程内缓存；**缺年份文件或 schema 缺字段一律返回空集结构
（不是报错）**——free_weekend 计算退化为「不考虑节假日」的现状语义，提议上下文
不含节假日事实，evidence 不出现 calendar 条目。与「Agent 不可用也不阻塞记录」
同一降级哲学。

测试用 `HOLIDAY_DATA_DIR` 指向受控的样例数据目录注入固定断言（架构第七节
fixed-value 策略）。
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("app.holidays")

_EMPTY: dict[str, Any] = {"year": None, "source": None, "updated_at": None, "holidays": {}, "workdays": {}}
_cache: dict[int, dict[str, Any]] = {}


def data_dir() -> Path:
    """数据目录。测试用 HOLIDAY_DATA_DIR 覆盖（UT-S03-41 的注入点）。"""
    import os

    override = os.environ.get("HOLIDAY_DATA_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data"


def empty() -> dict[str, Any]:
    """空集结构的独立副本。调用方不得原地修改。"""
    return {"year": None, "source": None, "updated_at": None, "holidays": {}, "workdays": {}}


def load_year(year: int) -> dict[str, Any]:
    """加载某年的节假日数据；缺失 / JSON 非法 / schema 缺字段一律返回空集。"""
    if year in _cache:
        return _cache[year]
    path = data_dir() / f"holidays_{year}.json"
    data = empty()
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            # 只认 schema 字段；类型不对的按空集处理（加载器只认 schema，架构 5.5）
            holidays = raw.get("holidays")
            workdays = raw.get("workdays")
            if isinstance(holidays, dict) and isinstance(workdays, dict):
                data = {
                    "year": raw.get("year", year),
                    "source": raw.get("source"),
                    "updated_at": raw.get("updated_at"),
                    "holidays": holidays,
                    "workdays": workdays,
                }
            else:
                logger.warning("holidays_schema_invalid", extra={"path": str(path)})
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("holidays_load_failed", extra={"error_type": type(exc).__name__})
    _cache[year] = data
    return data


def is_workday(day) -> bool:
    """该日期是否为法定调休上班日（多为周末）。数据缺失时恒为 False——安全退化。"""
    return day.isoformat() in load_year(day.year)["workdays"]


def upcoming_facts(today, limit: int = 3) -> list[str]:
    """未来 limit 个节假日事实的文案行（提议上下文用）。

    从今天起向后扫描一年；没有数据就没有事实行（EX-P.6 的上下文表现）。
    """
    data = load_year(today.year)
    facts: list[str] = []
    seen: set[str] = set()
    for offset in range(0, 366):
        day = today + timedelta(days=offset)
        year_data = data if day.year == today.year else load_year(day.year)
        name = year_data["holidays"].get(day.isoformat())
        if name and name not in seen:
            seen.add(name)
            days = sorted(d for d, n in year_data["holidays"].items() if n == name)
            span = f"{days[0]}–{days[-1]}" if len(days) > 1 else days[0]
            facts.append(f"{span} 是{name}假期")
            if len(facts) >= limit:
                break
    return facts


def reset_cache() -> None:
    """测试注入不同数据目录后清缓存。"""
    _cache.clear()


def next_holiday_occurrence(names, today):
    """在已加载数据的年份（当年 + 次年）里，找 names 中最早到来的节假日日期。

    返回 (date, 名称)；所选名称在数据中都找不到（含缺年份）时返回 None——
    调用方按 TIMING_INVALID 处理（显式选择的节假日算不出日期，宁可拒绝不可瞎猜）。
    """
    from datetime import date as _date

    wanted = set(names)
    for year in (today.year, today.year + 1):
        data = load_year(year)
        hits = []
        for day_str, name in data["holidays"].items():
            if name in wanted:
                day = _date.fromisoformat(day_str)
                if day >= today:
                    hits.append((day, name))
        if hits:
            return min(hits)
    return None


def holiday_names(year: int) -> list[str]:
    """某年数据中出现的节假日名（去重、按首次出现排序）。供 /holidays 枚举。"""
    seen: list[str] = []
    for _day, name in sorted(load_year(year)["holidays"].items()):
        if name not in seen:
            seen.append(name)
    return seen


def holiday_items(year: int) -> list[dict]:
    """某年全部节假日条目（date + name，按日期升序）。数据缺失返回空表。"""
    data = load_year(year)
    return [
        {"date": day, "name": name}
        for day, name in sorted(data["holidays"].items())
    ]
