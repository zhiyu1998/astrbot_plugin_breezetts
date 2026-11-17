# Breeze TTS 适配器

把 [Breeze](https://breeze.blue) 的 TTS 接口以 **插件** 方式注入 AstrBot，在 WebUI 的「文字转语音」里多出一个 **Breeze TTS** 提供商。不需要改动 AstrBot 任何源文件。

## 安装部署

### 环境要求

| 项目 | 要求 |
| --- | --- |
| AstrBot | v4.16 及以上（`metadata.yaml` 声明 `>=4.16,<5`） |
| Python | 3.10+，直接用 AstrBot 自带的虚拟环境 |
| 依赖 | 无，只用到 AstrBot 内置的 `httpx` |
| 网络 | 能访问 `api.breeze.blue`；不通时在提供商配置里填 `proxy` |

整个插件是纯 Python 单包，不需要 `pip install`，也不需要改 AstrBot 任何源文件。

### 方式一：面板安装（推荐）

AstrBot 面板 → **插件** → **安装插件**，填入仓库地址：

```
https://github.com/zhiyu1998/astrbot_plugin_breezetts
```

安装完点插件页的「重载」，或重启 AstrBot。

### 方式二：手动安装

1. 把插件放进 AstrBot 的 `data/plugins`：

```shell
cd /path/to/AstrBot
git clone https://github.com/zhiyu1998/astrbot_plugin_breezetts.git data/plugins/astrbot_plugin_breezetts
```

2. 重启 AstrBot（面板「重载插件」也行）。按部署方式选一条：

```shell
# 面板/源码部署
pm2 restart astrbot --update-env
# Docker 部署
docker compose restart astrbot
```

### 方式三：用 Release 包

到 [Releases](https://github.com/zhiyu1998/astrbot_plugin_breezetts/releases) 下载 `astrbot_plugin_breezetts.zip`，解压后目录结构必须是：

```text
data/plugins/astrbot_plugin_breezetts/
├── main.py
├── _provider.py
├── metadata.yaml
└── logo.png
```

即插件根目录下直接是 `main.py`，不要再套一层文件夹。放好后重启 AstrBot。

### 验证安装成功

三个都对就说明装好了：

1. 启动日志里有这一行：

   ```text
   [astrbot_plugin_breezetts.main] [breeze_tts] 提供商类型已注册：breeze_tts / ProviderType.TEXT_TO_SPEECH / Breeze TTS
   ```

2. WebUI → 配置 → 提供商 → **文字转语音** → 新增，类型下拉里能看到 **Breeze TTS**；

3. 填好 `api_key` 保存并重启后，日志出现 `Loading model breeze_tts(breeze_tts)`，且**没有** `Provider adapter not found`。

### 更新与卸载

- 更新：进插件目录 `git pull` 后重载；或在面板里卸载再装一次
- 卸载：删掉 `data/plugins/astrbot_plugin_breezetts`，再把 `data/cmd_config.json` 里 `breeze_tts` 那条提供商配置删掉（插件已注销时 AstrBot 会忽略该条目）

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

## 发版

推一个 `v*` tag 就会自动建 Release 并附上插件 zip（`.github/workflows/release.yml`）：

```bash
# 附注 tag 一定要带 --cleanup=verbatim，否则 Markdown 的 ## 标题会被当注释删掉
git tag -a v0.2.2 -F notes.md --cleanup=verbatim
git push origin v0.2.2
```

- Release 正文取自 tag 的说明，tag 没说明时用 GitHub 自动生成
- 资产是 `git archive` 出来的 `astrbot_plugin_breezetts.zip`，`.github`、`.gitignore`、`.gitattributes` 通过 `export-ignore` 排除
- 漏建了可以手动补：Actions → Release → Run workflow，填已有 tag

## 实现说明

- 主接口：`POST {api_base}/text-to-speech/{voice}?output_format=wav`
- 兜底：404/405 时自动尝试 OpenAI 风格的 `POST {api_base}/audio/speech`
- 返回的音频写入 `data/temp/breeze_tts_<id>.<fmt>` 后交给 AstrBot 发送
- `default_config_tmpl` 里带 `provider_type: text_to_speech`，WebUI 的 `availableSourceTypes` 才不会被过滤掉
- 插件 import 时向 `CONFIG_METADATA_2` 的 `config_template` 注入一个键名为 **Breeze TTS** 的模板（纯内存，不落盘、不改 AstrBot 源码），这样列表里显示的是「Breeze TTS」而不是原始类型名 `breeze_tts`
- 重写了 `test()`：WebUI 的「测试」按钮会真实合成一句话，key 不对/接口不通会直接把错误显示出来（基类 `TTSProvider` 默认的 `test()` 是空实现，永远显示可用）
