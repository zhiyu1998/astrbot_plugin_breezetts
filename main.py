"""Breeze TTS Adapter - AstrBot 插件入口"""

import asyncio

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from . import _balance

# 导入即触发 register_provider_adapter 注册 breeze_tts 类型
from ._provider import DEFAULT_API_BASE, PROVIDER_TYPE_NAME, ProviderBreezeTTS  # noqa: F401

# 每日奖励在北京时间 08:00 重置（服务端 00:00 UTC），错开几分钟再领
CLAIM_HOUR, CLAIM_MINUTE = 8, 5


@register("breeze_tts", "橘域网", "Breeze TTS 适配器", "0.2.4")
class BreezeTTSPlugin(Star):
    """Breeze TTS 适配器插件：注册提供商 + 余额查询 + 每日奖励。"""

    def __init__(self, context: Context, config=None) -> None:
        super().__init__(context)
        # AstrBot 把 _conf_schema.json 对应的插件配置作为第二个参数注入
        self.config = config
        self._claim_task: asyncio.Task | None = None
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

    # ---------- 每日奖励 ----------

    def _auto_claim_enabled(self) -> bool:
        cfg = _balance._as_mapping(self.config)
        return bool(cfg.get("AUTO_CLAIM_DAILY"))

    @filter.on_astrbot_loaded()
    async def start_auto_claim(self):
        """AstrBot 全部加载完成后启动自动领取任务（此时事件循环已就绪）。"""
        if not self._auto_claim_enabled():
            return
        if self._claim_task and not self._claim_task.done():
            return
        self._claim_task = asyncio.create_task(self._auto_claim_loop())
        logger.info("[breeze_tts] 已开启自动领取每日奖励（每天 08:05）")

    async def _auto_claim_loop(self) -> None:
        while True:
            delay = _balance.seconds_until_claim(CLAIM_HOUR, CLAIM_MINUTE)
            await asyncio.sleep(delay)
            try:
                text = await self.claim_daily()
                logger.info(f"[breeze_tts] 自动领取每日奖励：{text.splitlines()[0]}")
            except _balance.BalanceError as exc:
                logger.warning(f"[breeze_tts] 自动领取每日奖励失败：{exc}")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[breeze_tts] 自动领取每日奖励异常：{exc}")

    async def terminate(self) -> None:
        if self._claim_task and not self._claim_task.done():
            self._claim_task.cancel()
            try:
                await self._claim_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

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

    @filter.command(
        "breeze签到",
        alias={"breeze签到领取", "breeze领积分", "breeze领取"},
    )
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def claim_command(self, event: AstrMessageEvent):
        """领取 Breeze 每日积分奖励（网页端那个每日奖励）。"""
        try:
            text = await self.claim_daily()
        except _balance.BalanceError as exc:
            yield event.plain_result(f"❌ {exc}")
            return
        yield event.plain_result(text)

    async def claim_daily(self) -> str:
        """带 cookie 调 /api/credits/daily-claim；档位交给服务端按账号资质判定。"""
        settings = _balance.resolve_settings(
            self.context.get_config(), self.config
        )
        data = await _balance.claim_daily(
            settings["cookie"],
            web_base=settings["web_base"],
            timeout=settings["timeout"],
            proxy=settings["proxy"],
        )
        snippet = _balance.format_claim(data)
        try:
            snippet += "\n\n" + await self.query_balance()
        except _balance.BalanceError:
            pass
        return snippet

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
        """读取提供商配置 + 插件配置（WEB_COOKIE），合并两个数据源后排版。

        配置是每次调用时现读的，WebUI 里改完 cookie 立即生效，不用重启。
        """
        config = self.context.get_config()
        settings = _balance.resolve_settings(config, self.config)
        if not settings["has_provider"] and not settings["cookie"]:
            raise _balance.BalanceError(
                "还没有添加 Breeze TTS 提供商，先到 WebUI → 配置 → 提供商 → 文字转语音 里添加"
            )

        api_key = settings["api_key"]
        cookie = settings["cookie"]
        timeout = settings["timeout"]
        proxy = settings["proxy"]

        data: dict | None = None
        web: dict | None = None
        warns: list[str] = []

        if api_key:
            try:
                data = await _balance.fetch_balance(
                    settings["api_base"], api_key, timeout=timeout, proxy=proxy
                )
            except _balance.BalanceError as exc:
                warns.append(str(exc))

        if cookie:
            try:
                web = await _balance.fetch_web_summary(
                    cookie,
                    web_base=settings["web_base"],
                    timeout=timeout,
                    proxy=proxy,
                )
            except _balance.BalanceError as exc:
                warns.append(str(exc))

        if data is None and web is None:
            raise _balance.BalanceError(
                "；".join(warns) or "api_key 和 cookie 都没有配置，先在提供商配置里填一个"
            )

        return _balance.format_balance(data, web=web, warn="；".join(warns))