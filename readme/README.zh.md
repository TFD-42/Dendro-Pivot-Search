<div align="center">

# DendroPivot

### 注重隐私的 Python 本地网络搜索探索器 — 将一个查询转化为可导航的知识树

**无需 API 密钥。可选的本地 Ollama LLM。仅需 Python 标准库。**

DendroPivot 将单次搜索转化为有引导的探索路径。每轮中，种子查询会扩展为五个*聚焦*重新表述和五个*相邻*主题；您阅读的内容会强化知识树，任何结果都可以成为新的根节点。它可以在终端运行或作为本地实时网页，无需 API 密钥即可查询多个免费搜索索引，可通过 [Ollama](https://ollama.com) 使用本地 LLM，且仅需 Python 标准库。

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![许可证: MIT](https://img.shields.io/badge/license-MIT-green.svg)](../LICENSE)
[![无需 API 密钥](https://img.shields.io/badge/API%20密钥-不需要-success)](#搜索后端)

[English](../README.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Русский](README.ru.md) · **中文** · [日本語](README.ja.md) · [Português](README.pt.md)

</div>

---

## 为什么选择 DendroPivot？

单次搜索查询只能展示一个主题的某个角度。DendroPivot 将您的查询视为**种子**，将其展开为五个重新表述和五个相邻主题，针对多个免费搜索索引运行它们，并利用您实际打开的内容来引导下一轮。结果是一棵探索树，而不是十个链接的平面列表。

## 枢转方法论

| 步骤 | 发生什么 | 为何有效 |
|---|---|---|
| 1. **种子** | 输入初始查询。 | 建立树的根节点。 |
| 2. **分支** | 展开为 5 个聚焦角度和 5 个相邻主题。 | 多视角而非单一排名。 |
| 3. **阅读** | 打开结果会强化其词汇。 | 您的兴趣引导下一轮。 |
| 4. **生长** | 新轮次将查询锚定在共同术语上。 | 领域核心概念变得可见。 |
| 5. **枢转** | 按 `f` 或 Shift+点击：结果成为新根节点。 | 深入子主题而不失去上下文。 |
| 6. **返回** | 历史记录保存每棵树；`b`/`n` 导航。 | 比较分支并随时返回。 |

## 功能特点

- **每轮两列**：聚焦（5 个重新表述）+ 相邻（5 个相关主题）
- **持续丰富**：已读结果影响下一轮
- **多后端搜索**：Bing RSS、Marginalia、Yahoo、DDG Lite — 带轮换、回退和冷却
- **HTML 优先**：在浏览器中打开实时树；终端外创建 HTML 快照
- **六种语言**：`--lang fr|en|es|it|zh|ru`
- **可选 Ollama**：LLM 查询扩展和按需翻译
- **仅标准库**：无需 `pip install`，适用于 Python 3.10+ 的任何环境

## 系统要求

| 组件 | 要求 |
|---|---|
| Python | **3.10 或更高版本** |
| 网络 | 到搜索后端的出站 HTTPS |
| Ollama | 可选，仅用于 LLM 扩展和翻译 |
| Python 包 | 无 |

## 安装

```bash
git clone https://github.com/TFD-42/dendropivot-search.git
cd dendropivot-search
python3 websearch.py -q "本地语言模型"
```

## 快速开始

```bash
# 浏览器中的实时 HTML 树（在终端中运行时的默认值）
python3 websearch.py -q "机器学习"

# 单轮 JSON 输出
python3 websearch.py -q "机器学习" --rounds 1 --no-ollama --json

# 双列终端界面
python3 websearch.py -q "机器学习" --tui
```

## 输出模式

| 上下文 | 默认输出 | 覆盖 |
|---|---|---|
| 从终端 | `http://127.0.0.1:8765/` 的实时 HTML 树 | `--tui`、`--json`、`--text` |
| 管道/脚本（无 TTY） | 当前目录中的 HTML 快照 | `--html-out 路径`、`--json` |

## 命令行选项

| 选项 | 默认值 | 描述 |
|---|---|---|
| `-q`、`--query 文本` | 提示 | 初始种子查询 |
| `-n`、`--limit N` | `6` | 每次查询的最大结果数 |
| `--interval 秒` | `60` | 轮次间的延迟 |
| `--rounds N` | `0` | 轮数（0 = 无限） |
| `--lang 代码` | 自动 | `fr`、`en`、`es`、`it`、`zh`、`ru` |
| `--no-ollama` | 关 | 仅启发式扩展 |
| `--tui` | 关 | 终端界面 |
| `--json` | 关 | JSON 到 stdout |
| `--text` | 关 | 纯文本到 stdout |
| `--html-out 路径` | 自动 | 快照路径 |

## 搜索后端

| 后端 | 端点 | 备注 |
|---|---|---|
| `bing-rss` | `bing.com/search?format=rss` | 结构化 RSS |
| `marginalia` | `old-search.marginalia.nu` | 独立索引 |
| `yahoo` | `search.yahoo.com` | HTML 解析 |
| `ddg-lite` | `lite.duckduckgo.com/lite/` | 基于 POST |

## 许可证

在 [MIT 许可证](../LICENSE) 下发布。

---

<div align="center">

由 [@TFD-42](https://github.com/TFD-42) 维护 · [报告 Bug](https://github.com/TFD-42/dendropivot-search/issues/new?template=bug_report.yml)

</div>
