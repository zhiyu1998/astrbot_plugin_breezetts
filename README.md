# Breeze TTS 适配器

把 [Breeze](https://breeze.blue) 的 TTS 接口以 **插件** 方式注入 AstrBot，在 WebUI 的「文字转语音」里多出一个 **Breeze TTS** 提供商。不需要改动 AstrBot 任何源文件。

## 安装

```bash
cd /path/to/AstrBot/data/plugins
git clone <repo> astrbot_plugin_breezetts
# 重启或重载插件
```

## 使用

1. WebUI → 配置 → 提供商 → **文字转语音** 标签页
2. 点「新增」，类型选 **Breeze TTS**
3. 填 `api_key`（必填）、`api_base`、`model`、`voice`
4. 保存后在 TTS 设置里选它作为默认提供商

## 配置项

| 字段 | 说明 | 默认 |
| --- | --- | --- |
| `api_key` | Breeze API 密钥 | 空 |
| `api_base` | 接口地址 | `https://api.breeze.blue/v1` |
| `model` | 模型 ID | `breeze-tts-2` |
| `voice` | 音色 ID | `voc_8yud7hz7c9q2` |
| `output_format` | 输出格式 | `wav` |
| `language_code` | 语言 | `zh` |
| `timeout` | 超时（秒） | `60` |
| `proxy` | HTTP 代理 | 空 |

## 实现说明

- 主接口：`POST {api_base}/text-to-speech/{voice}?output_format=wav`
- 兜底：404/405 时自动尝试 OpenAI 风格的 `POST {api_base}/audio/speech`
- 返回的音频写入 `data/temp/breeze_tts_<id>.<fmt>` 后交给 AstrBot 发送
- `default_config_tmpl` 里带 `provider_type: text_to_speech`，WebUI 的 `availableSourceTypes` 才不会被过滤掉
- 插件 import 时向 `CONFIG_METADATA_2` 的 `config_template` 注入一个键名为 **Breeze TTS** 的模板（纯内存，不落盘、不改 AstrBot 源码），这样列表里显示的是「Breeze TTS」而不是原始类型名 `breeze_tts`
- 重写了 `test()`：WebUI 的「测试」按钮会真实合成一句话，key 不对/接口不通会直接把错误显示出来（基类 `TTSProvider` 默认的 `test()` 是空实现，永远显示可用）
