"""Breeze TTS 适配器 —— 以插件形式向 AstrBot 注册 breeze_tts 提供商类型。

为什么之前「注册成功但界面上看不到」：
WebUI 的提供商类型列表由 dashboard/src/composables/useProviderSources.ts 的
availableSourceTypes 生成，筛选条件是 `template.provider_type === 当前标签页`。
provider_registry 里没有 provider_type 字段时，这一项会被直接过滤掉。
所以模板里必须显式带 "provider_type": "text_to_speech"。

另外，服务端把模板写进 config_template 时用的键是 provider.type（即 breeze_tts），
而前端直接用这个键当展示名。这里额外往 CONFIG_METADATA_2 注入一个显示名
"Breeze TTS" 的模板（内存操作，不改任何文件），列表里就不会是原始类型名。
"""

from __future__ import annotations

import os

import httpx

from astrbot.api import logger
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.provider import TTSProvider
from astrbot.core.provider.register import register_provider_adapter
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.datetime_utils import generate_timestamp_id

PROVIDER_TYPE_NAME = "breeze_tts"
DISPLAY_NAME = "Breeze TTS"
DEFAULT_API_BASE = "https://api.breeze.blue/v1"
DEFAULT_MODEL = "breeze-tts-2"
DEFAULT_VOICE = "voc_8yud7hz7c9q2"

DEFAULT_CONFIG_TMPL = {
    "id": PROVIDER_TYPE_NAME,
    "type": PROVIDER_TYPE_NAME,
    "provider": "breeze",
    # 关键字段：WebUI 靠它把这一项归到「文字转语音」标签页
    "provider_type": "text_to_speech",
    "enable": True,
    "api_key": "",
    "api_base": DEFAULT_API_BASE,
    "model": DEFAULT_MODEL,
    "voice": DEFAULT_VOICE,
    "output_format": "wav",
    "language_code": "zh",
    "timeout": 60,
    "proxy": "",
}


def _inject_display_template() -> bool:
    """往 config_template 注入一个显示名为 Breeze TTS 的模板。

    注入成功则注册适配器时不再提供 default_config_tmpl，避免列表里出现
    breeze_tts 与 Breeze TTS 两个重复项。
    """
    try:
        from astrbot.core.config.default import CONFIG_METADATA_2

        root = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
            "config_template"
        ]
        root[DISPLAY_NAME] = dict(DEFAULT_CONFIG_TMPL)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[breeze_tts] 注入显示名模板失败，回退为类型名：{exc}")
        return False


_injected = _inject_display_template()

_decorator = register_provider_adapter(
    PROVIDER_TYPE_NAME,
    "Breeze TTS",
    provider_type=ProviderType.TEXT_TO_SPEECH,
    default_config_tmpl=None if _injected else DEFAULT_CONFIG_TMPL,
    provider_display_name=DISPLAY_NAME,
)


def _register_once(cls):
    """插件热重载时避免重复注册抛 ValueError。"""
    try:
        return _decorator(cls)
    except ValueError:
        logger.debug("[breeze_tts] 提供商类型已注册，跳过重复注册")
        return cls


@_register_once
class ProviderBreezeTTS(TTSProvider):
    """Breeze TTS 提供商适配器。

    主接口: POST {api_base}/text-to-speech/{voice}?output_format=wav
    兜底接口: POST {api_base}/audio/speech（OpenAI 风格）
    """

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = self._read_key(provider_config)
        self.api_base = str(provider_config.get("api_base") or DEFAULT_API_BASE).rstrip("/")
        self.voice = str(provider_config.get("voice") or DEFAULT_VOICE)
        self.output_format = str(provider_config.get("output_format") or "wav").lstrip(".")
        self.language_code = str(provider_config.get("language_code") or "zh")
        self.proxy = str(provider_config.get("proxy") or "")
        try:
            self.timeout = float(provider_config.get("timeout") or 60)
        except (TypeError, ValueError):
            self.timeout = 60.0
        self.set_model(str(provider_config.get("model") or DEFAULT_MODEL))

    @staticmethod
    def _read_key(provider_config: dict) -> str:
        key = provider_config.get("api_key")
        if isinstance(key, str) and key.strip():
            return key.strip()
        raw = provider_config.get("key")
        if isinstance(raw, list) and raw:
            return str(raw[0]).strip()
        if isinstance(raw, str):
            return raw.strip()
        return ""

    def _headers(self) -> dict:
        headers = {"Accept": "audio/*,application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def get_audio(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            raise ValueError("Breeze TTS: 待合成文本为空")

        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)
        path = os.path.join(
            temp_dir,
            f"breeze_tts_{generate_timestamp_id()}.{self.output_format}",
        )

        client_kwargs: dict = {"timeout": self.timeout}
        if self.proxy:
            client_kwargs["proxy"] = self.proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await self._post_breeze(client, text)
            if resp.status_code in (404, 405):
                logger.debug("[breeze_tts] 主接口不可用，尝试 OpenAI 风格 /audio/speech")
                resp = await self._post_openai_style(client, text)
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Breeze TTS 请求失败 HTTP {resp.status_code}: {resp.text[:300]}"
                )
            audio = resp.content

        if not audio:
            raise RuntimeError("Breeze TTS 返回空音频")
        if audio[:1] in (b"{", b"["):
            raise RuntimeError(f"Breeze TTS 返回的不是音频数据: {audio[:200]!r}")

        with open(path, "wb") as f:
            f.write(audio)
        logger.debug(f"[breeze_tts] 合成完成 {len(audio)} bytes -> {path}")
        return path

    async def _post_breeze(self, client: httpx.AsyncClient, text: str) -> httpx.Response:
        url = f"{self.api_base}/text-to-speech/{self.voice}"
        payload = {
            "text": text,
            "model_id": self.model_name,
            "language_code": self.language_code,
        }
        return await client.post(
            url,
            params={"output_format": self.output_format},
            json=payload,
            headers=self._headers(),
        )

    async def _post_openai_style(
        self, client: httpx.AsyncClient, text: str
    ) -> httpx.Response:
        url = f"{self.api_base}/audio/speech"
        payload = {
            "model": self.model_name,
            "input": text,
            "voice": self.voice,
            "response_format": self.output_format,
        }
        return await client.post(url, json=payload, headers=self._headers())

    async def test(self) -> None:
        """WebUI 的「测试」按钮：真实合成一句短文本，验证 key / 接口 / 音色。

        基类 TTSProvider 没有重写 test()，默认实现直接返回，按钮永远显示可用，
        这里补上真实探测，失败时异常文本会原样显示在 WebUI 上。
        """
        path = await self.get_audio("你好，这是一条语音合成测试。")
        try:
            size = os.path.getsize(path)
            if size < 44:
                raise RuntimeError(f"Breeze TTS 返回的音频过小（{size} bytes）")
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    async def terminate(self) -> None:
        return None
