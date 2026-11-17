"""余额查询：GET {api_base}/balance（`xi-api-key` 认证）。

breeze.blue 的开发者后台显示的那个 "Current Balance"，对应的就是
`GET https://api.breeze.blue/v1/balance`，返回体除了 balance 还带
最近若干条 charges（每次合成的扣费明细），可以直接拿来算「今日消耗」。

注意：网页会话用的是 cookie，而 API Key 走的是 `xi-api-key` 头，两者不通用。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

TZ_CN = timezone(timedelta(hours=8))
BALANCE_PATH = "/balance"
DEFAULT_TIMEOUT = 30.0


class BalanceError(RuntimeError):
    """余额查询失败（提示信息直接展示给用户）。"""


async def fetch_balance(
    api_base: str,
    api_key: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    proxy: str = "",
) -> dict:
    """查询余额，返回 /v1/balance 的 JSON（额外塞入 _key_id）。"""
    key = (api_key or "").strip()
    if not key:
        raise BalanceError("还没有填写 Breeze API Key，先到提供商配置里填上")

    url = f"{(api_base or '').rstrip('/')}{BALANCE_PATH}"
    headers = {"xi-api-key": key, "Accept": "application/json"}
    client_kwargs: dict = {"timeout": timeout, "follow_redirects": True}
    if proxy:
        client_kwargs["proxy"] = proxy

    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
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


def format_balance(data: dict) -> str:
    """/v1/balance 的 JSON → 适合直接发到聊天里的多行文本。"""
    balance = float(data.get("balance") or 0)
    charges = [c for c in (data.get("charges") or []) if isinstance(c, dict)]

    lines = [f"💳 Breeze 余额：{_num(balance)} 积分"]

    today = datetime.now(TZ_CN).date()
    spent_today = 0.0
    count_today = 0
    for charge in charges:
        when = _parse_time(charge.get("created_at"))
        if when and when.date() == today:
            spent_today += float(charge.get("amount") or 0)
            count_today += 1

    if charges:
        lines.append(f"📅 今日消耗：{_num(spent_today)} 积分 · {count_today} 次")
        last = charges[0]
        when = _parse_time(last.get("created_at"))
        amount = float(last.get("amount") or 0)
        detail = f"（{last['text_characters']} 字）" if last.get("text_characters") else ""
        prefix = f"{when:%H:%M} " if when else ""
        lines.append(f"🕒 最近：{prefix}{_charge_label(last)} {_num(amount)} 积分{detail}")
    else:
        lines.append("📅 今日消耗：暂无记录")

    if data.get("settlement_pending"):
        lines.append("⏳ 有消费尚未结算，余额可能略滞后")

    key_id = data.get("_key_id") or ""
    if key_id:
        lines.append(f"🔑 密钥：{key_id}")

    return "\n".join(lines)


def pick_provider_config(config) -> dict | None:
    """从 AstrBot 全局配置里找出 Breeze TTS 提供商的配置项。"""
    try:
        providers = config.get("provider") or []
    except AttributeError:
        providers = []
    fallback = None
    for item in providers:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "") != "breeze_tts":
            continue
        if item.get("api_key") or item.get("key"):
            return item
        fallback = fallback or item
    return fallback