"""天气数据源（weather-data-source，架构 5.8）。

WeatherProvider 抽象与 Open-Meteo 兼容实现。位置唯一来源是用户在 P6 声明的
偏好 `pref_key='location'`——不使用 IP 推断、不使用浏览器定位、不做静默采集。
未声明城市 / 供应商不可用 / 超时 5 秒 → 返回 None，上下文静默跳过天气事实
（与「Agent 不可用也不阻塞」同一降级哲学）。

天气是瞬时预报：不写入 evidence、不持久化、不建提醒（proposal 边界）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger("app.weather")


@dataclass(frozen=True)
class WeatherFact:
    date: str  # YYYY-MM-DD
    summary: str  # 日级趋势摘要，如「小雨，12–18°C」


class WeatherProvider(Protocol):
    async def forecast(self, *, city: str, days: int = 14) -> list[WeatherFact] | None: ...


class OpenMeteoProvider:
    """Open-Meteo 兼容实现（geocoding + forecast 两段查询）。

    base_url 由 WEATHER_BASE_URL 注入（默认官方端点）；任何同类兼容服务可替换。
    失败 / 超时返回 None——不阻塞、不重试队列（架构 5.8 降级约定）。
    """

    def __init__(self) -> None:
        import httpx

        from app.config import get_settings

        s = get_settings()
        self._base = s.WEATHER_BASE_URL.rstrip("/")
        self._client = httpx.AsyncClient(timeout=5.0)

    async def forecast(self, *, city: str, days: int = 14) -> list[WeatherFact] | None:
        try:
            geo = await self._client.get(
                f"{self._base}/geocoding/search", params={"name": city, "count": 1, "language": "zh"}
            )
            results = geo.json().get("results") or []
            if not results:
                return None
            lat, lon = results[0]["latitude"], results[0]["longitude"]
            fc = await self._client.get(
                f"{self._base}/forecast",
                params={"latitude": lat, "longitude": lon, "daily": "weathercode,temperature_2m_max,temperature_2m_min", "forecast_days": days, "timezone": "auto"},
            )
            daily = fc.json().get("daily") or {}
            dates = daily.get("time") or []
            codes = daily.get("weathercode") or []
            tmax = daily.get("temperature_2m_max") or []
            tmin = daily.get("temperature_2m_min") or []
            facts = [
                WeatherFact(
                    date=d,
                    summary=f"{_WEATHER_TEXT_ZH.get(int(c), '多云')}，{round(tlo)}–{round(thi)}°C",
                )
                for d, c, thi, tlo in zip(dates, codes, tmax, tmin)
            ]
            return facts or None
        except Exception as exc:  # noqa: BLE001 —— 网络错误 / 超时 / 解析失败一律静默降级
            logger.warning("weather_unavailable", extra={"error_type": type(exc).__name__})
            return None


# WMO weathercode 的中文摘要（只覆盖常见区间，其余归为「多云」）
_WEATHER_TEXT_ZH: dict[int, str] = {
    0: "晴", 1: "大致晴", 2: "多云", 3: "阴",
    45: "雾", 48: "雾凇",
    51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    71: "小雪", 73: "中雪", 75: "大雪",
    80: "阵雨", 81: "阵雨", 82: "强阵雨",
    95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "雷阵雨伴冰雹",
}


def default_weather_provider() -> str:
    return "open-meteo"


_provider: WeatherProvider | None = None


def get_weather_provider() -> WeatherProvider | None:
    """按配置返回 Provider；未配置 WEATHER_BASE_URL 时返回 None（能力整体静默）。"""
    global _provider
    if _provider is None:
        from app.config import get_settings

        if not get_settings().WEATHER_BASE_URL:
            return None
        _provider = OpenMeteoProvider()
    return _provider


def set_weather_provider(provider: WeatherProvider | None) -> None:
    """测试注入点（fixed-value 策略）。"""
    global _provider
    _provider = provider


def reset_weather_cache() -> None:
    """测试间清空城市级缓存。"""
    _city_cache.clear()


# 城市级缓存：6 小时内同一城市不重复打外部端点（架构 5.8）
import time as _time

_city_cache: dict[str, tuple[float, list[WeatherFact]]] = {}
_CITY_CACHE_TTL = 6 * 3600


async def cached_forecast(city: str) -> list[WeatherFact] | None:
    """带进程内缓存的 forecast（6 小时 TTL）。"""
    provider = get_weather_provider()
    if provider is None or not city:
        return None
    now = _time.monotonic()
    hit = _city_cache.get(city)
    if hit is not None and now - hit[0] < _CITY_CACHE_TTL:
        return hit[1]
    facts = await provider.forecast(city=city)
    if facts is not None:
        _city_cache[city] = (now, facts)
    return facts
