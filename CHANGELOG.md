# Changelog

## v0.2.3
- 新增：插件配置项 `WEB_COOKIE`（网页 Cookie）与 `WEB_BASE`。填了 cookie 后余额里会多出套餐、今日签到可领等信息。
- 改：余额查询同时支持 API Key 与网页 Cookie 两条数据源，任一可用即可；cookie 失效只会多一行提示，不影响 api_key 的余额显示。
- 改：每次调用都现读配置（提供商配置 + `data/config/astrbot_plugin_breezetts_config.json`），WebUI 里换 cookie 立即生效，不用重启。

## v0.2.2
- 新增：`breeze余额` 指令（别名 `breeze余额查询` / `breeze查余额` / `breeze积分`，仅管理员），显示 Breeze 账户的 Current Balance、今日消耗与最近一次扣费。
- 新增：LLM 工具 `breeze_balance`，在对话里问「还有多少余额」时由模型自动调用。
- 余额查询走 `GET {api_base}/balance`（`xi-api-key` 认证），复用提供商配置里的 `api_key`，不需要再填一遍。

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
