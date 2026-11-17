"""Breeze TTS Adapter - AstrBot 插件入口"""

from astrbot.api import logger
from astrbot.api.star import Context, Star, register

# 导入即触发 register_provider_adapter 注册 breeze_tts 类型
from ._provider import PROVIDER_TYPE_NAME, ProviderBreezeTTS  # noqa: F401


@register("breeze_tts", "橘域网", "Breeze TTS 适配器", "0.2.1")
class BreezeTTSPlugin(Star):
    """Breeze TTS 适配器插件（只注册提供商，不注册任何指令）"""

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
