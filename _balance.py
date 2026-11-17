"""余额查询：官方 API 走 `GET {api_base}/balance`，网页接口走 cookie。

两条数据源：

1. **API Key**（`xi-api-key` 头）→ `GET /v1/balance`
   拿得到精确余额、millicredits，以及最近若干条 charges（每次合成的扣费明细）。
2. **网页 Cookie**（登录 breezeblue.ai 后的会话）→ `GET /api/credits/summary`
   拿得到会员等级、每日可领额度、今日是否已领这类只有网页端才有的信息。

两者互相独立：只填 api_key 也能用（余额 + 今日消耗）；填了 cookie 会多出
会员/签到信息，且 api_key 缺失时还能单独用 cookie 兜底。

cookie 是会话凭证，会过期。插件每次调用都重新读配置，WebUI 里改完立即生效，
不需要重启。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import httpx

TZ_CN = timezone(timedelta(hours=8))
BALANCE_PATH = "/balance"
SUMMARY_PATH = "/api/credits/summary"
ENTITLEMENT_PATH = "/api/billing/entitlements"
DEFAULT_TIMEOUT = 30.0
DEFAULT_WEB_BASE = "https://breezeblue.ai"
WEB_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class BalanceError(RuntimeError):
    """余额查询失败（提示信息直接展示给用户）。"""


class CookieExpired(BalanceError):
    """网页 Cookie 失效（401/403）。"""


def _client_kwargs(timeout: float, proxy: str) -> dict:
    kwargs: dict = {"timeout": timeout, "follow_redirects": True}
    if proxy:
        kwargs["proxy"] = proxy
    return kwargs


async def fetch_balance(
    api_base: str,
    api_key: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    proxy: str = "",
) -> dict:
    """API Key 查询余额，返回 /v1/balance 的 JSON（额外塞入 _key_id）。"""
    key = (api_key or "").strip()
    if not key:
        raise BalanceError("还没有填写 Breeze API Key，先到提供商配置里填上")

    url = f"{(api_base or '').rstrip('/')}{BALANCE_PATH}"
    headers = {"xi-api-key": key, "Accept": "application/json"}

    try:
        async with httpx.AsyncClient(**_client_kwargs(timeout, proxy)) as client:
            resp = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise BalanceError(f"连接 Breeze 失败：{exc}") from exc

    if resp.status_code in (401, 403):
        raise BalanceError(f"API Key 无效或被禁用（HTTP {resp.status_code}）")
    if resp.status_code == 404:
        raise BalanceError(f"接口不支持余额查询（HTTP 404，{url}）")
    if resp.status_code >= 400:
        raise BalanceError(f"查询失败 HTTP {resp.status_code}：{resp.text[:200]}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise BalanceError(f"返回内容不是 JSON：{resp.text[:200]}") from exc
    if not isinstance(data, dict):
        raise BalanceError(f"返回内容格式异常：{str(data)[:200]}")

    data["_key_id"] = resp.headers.get("x-breeze-api-key-id", "")
    return data


async def fetch_web_summary(
    cookie: str,
    *,
    web_base: str = DEFAULT_WEB_BASE,
    timeout: float = DEFAULT_TIMEOUT,
    proxy: str = "",
) -> dict:
    """用网页 Cookie 拉 /api/credits/summary 与 /api/billing/entitlements。"""
    jar = (cookie or "").strip()
    if not jar:
        raise BalanceError("没有配置网页 Cookie")
    if jar.lower().startswith("cookie:"):
        jar = jar.split(":", 1)[1].strip()

    base = (web_base or DEFAULT_WEB_BASE).rstrip("/")
    headers = {
        "Cookie": jar,
        "Accept": "application/json",
        "User-Agent": WEB_USER_AGENT,
        "Referer": f"{base}/app/developer",
    }

    summary: dict = {}
    entitlements: dict = {}
    try:
        async with httpx.AsyncClient(**_client_kwargs(timeout, proxy)) as client:
            resp = await client.get(f"{base}{SUMMARY_PATH}", headers=headers)
            if resp.status_code in (401, 403):
                raise CookieExpired("网页 Cookie 已失效，去后台重新复制一份")
            if resp.status_code < 400:
                summary = resp.json() or {}

            resp2 = await client.get(f"{base}{ENTITLEMENT_PATH}", headers=headers)
            if resp2.status_code < 400:
                entitlements = resp2.json() or {}
    except httpx.HTTPError as exc:
        raise BalanceError(f"连接 Breeze 网页接口失败：{exc}") from exc

    if not isinstance(summary, dict) or not summary:
        raise BalanceError("网页接口没有返回余额数据（Cookie 可能不完整）")

    return {"summary": summary, "entitlements": entitlements if isinstance(entitlements, dict) else {}}


def _num(value: float) -> str:
    return f"{value:,.2f}"


def _parse_time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).astimezone(TZ_CN)
    except ValueError:
        return None


def _charge_label(charge: dict) -> str:
    endpoint = str(charge.get("endpoint") or "")
    if "text-to-speech" in endpoint:
        return "语音合成"
    if endpoint:
        return endpoint.split("?")[0]
    return "调用"


def format_balance(
    data: dict | None,
    *,
    web: dict | None = None,
    warn: str = "",
) -> str:
    """把 /v1/balance（API Key）与网页 summary 合成一段聊天文本。"""
    data = data or {}
    summary = (web or {}).get("summary") or {}
    entitlements = (web or {}).get("entitlements") or {}

    balance = data.get("balance")
    if balance is None:
        balance = summary.get("balance")
    lines = ["💳 Breeze 余额：—" if balance is None else f"💳 Breeze 余额：{_num(float(balance))} 积分"]

    charges = [c for c in (data.get("charges") or []) if isinstance(c, dict)]
    today = datetime.now(TZ_CN).date()

    if charges:
        spent_today = 0.0
        count_today = 0
        for charge in charges:
            when = _parse_time(charge.get("created_at"))
            if when and when.date() == today:
                spent_today += float(charge.get("amount") or 0)
                count_today += 1
        lines.append(f"📅 今日消耗：{_num(spent_today)} 积分 · {count_today} 次")

        last = charges[0]
        when = _parse_time(last.get("created_at"))
        amount = float(last.get("amount") or 0)
        detail = f"（{last['text_characters']} 字）" if last.get("text_characters") else ""
        prefix = f"{when:%H:%M} " if when else ""
        lines.append(f"🕒 最近：{prefix}{_charge_label(last)} {_num(amount)} 积分{detail}")
    elif summary:
        spent = summary.get("consumed_total")
        if spent is not None:
            lines.append(f"📅 累计消耗：{_num(float(spent))} 积分")
    else:
        lines.append("📅 今日消耗：暂无记录")

    plan = entitlements.get("plan_code") or entitlements.get("status")
    if plan:
        lines.append(f"🏷️ 套餐：{plan}")

    if summary.get("daily_claim_available"):
        amount = summary.get("daily_claim_amount")
        hint = f"（{_num(float(amount))} 积分）" if amount is not None else ""
        lines.append(f"🎁 今日签到可领{hint}")

    if data.get("settlement_pending") or summary.get("settlement_pending"):
        lines.append("⏳ 有消费尚未结算，余额可能略滞后")

    key_id = data.get("_key_id") or ""
    if key_id:
        lines.append(f"🔑 密钥：{key_id}")

    if warn:
        lines.append(f"⚠️ {warn}")

    return "\n".join(lines)


def _read_disk_config() -> dict:
    """从 AstrBot 的 cmd_config.json 读一份配置（用于取最新写入的值）。"""
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path

        path = os.path.join(str(get_astrbot_data_path()), "cmd_config.json")
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


PLUGIN_CONFIG_FILENAME = "astrbot_plugin_breezetts_config.json"


def read_plugin_config() -> dict:
    """读插件自己的配置（data/config/astrbot_plugin_breezetts_config.json）。

    每次调用现读文件，这样 WebUI 里改 WEB_COOKIE 后立即生效，不必重启插件。
    """
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path

        path = os.path.join(
            str(get_astrbot_data_path()), "config", PLUGIN_CONFIG_FILENAME
        )
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _as_mapping(value) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return dict(value)
    except (TypeError, ValueError):
        return {}


def resolve_settings(config, plugin_config=None) -> dict:
    """合并「提供商配置」与「插件配置」，插件配置优先（cookie 更常在插件页改）。"""
    provider = pick_provider_config(config) or {}
    plugin = _as_mapping(plugin_config) or read_plugin_config()

    try:
        timeout = float(provider.get("timeout") or DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT

    return {
        "api_key": str(provider.get("api_key") or provider.get("key") or ""),
        "api_base": str(provider.get("api_base") or "https://api.breeze.blue/v1"),
        "cookie": str(plugin.get("WEB_COOKIE") or provider.get("cookie") or ""),
        "web_base": str(
            plugin.get("WEB_BASE") or provider.get("web_base") or DEFAULT_WEB_BASE
        ),
        "proxy": str(provider.get("proxy") or ""),
        "timeout": timeout,
        "has_provider": bool(provider),
    }


def pick_provider_config(config) -> dict | None:
    """找出 Breeze TTS 提供商配置，并用磁盘上的新值补齐。

    WebUI 保存后内存里的 AstrBotConfig 不一定立刻反映 cookie / api_key 的改动，
    这里以内存为准、磁盘补空值，保证「改完立即生效」。
    """
    live: dict | None = None
    try:
        providers = config.get("provider") or []
    except AttributeError:
        providers = []

    for item in providers:
        if isinstance(item, dict) and str(item.get("type") or "") == "breeze_tts":
            if item.get("api_key") or item.get("key") or item.get("cookie"):
                live = item
                break
            live = live or item

    disk = None
    for item in _read_disk_config().get("provider") or []:
        if isinstance(item, dict) and str(item.get("type") or "") == "breeze_tts":
            disk = item
            break

    if live is None:
        return disk
    if disk is None:
        return live

    merged = dict(live)
    for field in ("api_key", "key", "cookie", "api_base", "web_base", "proxy", "timeout"):
        if not merged.get(field) and disk.get(field):
            merged[field] = disk[field]
    return merged