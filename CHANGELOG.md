# Changelog

## v0.2.1
- 新增：向 `CONFIG_METADATA_2` 注入显示名模板，WebUI 「文字转语音 → 新增」列表显示为 **Breeze TTS**，不再是原始类型名 `breeze_tts`。
- 新增：真实 `test()` 实现，WebUI 的「测试」按钮会实际合成一句短文本，能暴露 401/超时/非音频响应等问题。
- 修正：注入成功时注册适配器传 `default_config_tmpl=None`，避免列表里同时出现 `breeze_tts` 与 `Breeze TTS` 两项。

## v0.2.0
- 修复：提供商在 WebUI 「文字转语音」列表里不显示。原因是 `default_config_tmpl` 缺少 `provider_type` 字段，前端 `availableSourceTypes` 按该字段过滤。
- 新增 OpenAI 风格 `/audio/speech` 兜底。
- 插件热重载时不再因重复注册抛 `ValueError`。
- 增加空文本、非音频响应、HTTP 错误的明确报错。

## v0.1.0
- 初始版本。
