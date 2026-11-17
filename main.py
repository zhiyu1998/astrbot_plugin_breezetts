"""Breeze TTS Adapter - AstrBot 插件入口"""

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from . import _balance

# 导入即触发 register_provider_adapter 注册 breeze_tts 类型
from ._provider import DEFAULT_API_BASE, PROVIDER_TYPE_NAME, ProviderBreezeTTS  # noqa: F401


@register("breeze_tts", "橘域网", "Breeze TTS 适配器", "0.2.2")
class BreezeTTSPlugin(Star):
    """Breeze TTS 适配器插件：注册提供商 + 余额查询指令。"""

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        from astrbot.core.provider.register import provider_cls_map

        meta = provider_cls_map.get(PROVIDER_TYPE_NAME)
        if meta:
            logger.info(
                f"[breeze_tts] 提供商类型已注册：{meta.type} / "
                f"{meta.provider_type} / {meta.provider_display_name}；"
                "请到 WebUI → 配置 → 提供商 → 文字转语音 里添加"
            )
        else:
            logger.error("[breeze_tts] 提供商注册失败：provider_cls_map 中找不到 breeze_tts")

    @filter.command(
        "breeze余额",
        alias={"breeze余额查询", "breeze查余额", "breeze积分"},
    )
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def balance_command(self, event: AstrMessageEvent):
        """查询 Breeze 账户当前余额与今日消耗。"""
        try:
            text = await self.query_balance()
        except _balance.BalanceError as exc:
            yield event.plain_result(f"❌ {exc}")
            return
        yield event.plain_result(text)

    @filter.llm_tool(name="breeze_balance")
    async def balance_tool(self, event: AstrMessageEvent) -> str:
        """查询 Breeze（breeze.blue）语音合成账户的剩余积分余额和今日消耗。

        Returns:
            string: 余额、今日消耗、最近一次扣费的文本摘要
        """
        try:
            return await self.query_balance()
        except _balance.BalanceError as exc:
            return f"查询失败：{exc}"

    async def query_balance(self) -> str:
        """读取提供商配置里的 api_key / api_base，请求 /v1/balance 并排版。"""
        config = self.context.get_config()
        provider_config = _balance.pick_provider_config(config)
        if not provider_config:
            raise _balance.BalanceError(
                "还没有添加 Breeze TTS 提供商，先到 WebUI → 配置 → 提供商 → 文字转语音 里添加"
            )

        try:
            timeout = float(provider_config.get("timeout") or _balance.DEFAULT_TIMEOUT)
        except (TypeError, ValueError):
            timeout = _balance.DEFAULT_TIMEOUT

        data = await _balance.fetch_balance(
            str(provider_config.get("api_base") or DEFAULT_API_BASE),
            str(provider_config.get("api_key") or ""),
            timeout=timeout,
            proxy=str(provider_config.get("proxy") or ""),
        )
        return _balance.format_balance(data)