<div align="center">

# DendroPivot

### プライバシー重視の Python ローカル Web 検索エクスプローラー — 1 つのクエリをナビゲート可能な知識ツリーに変換

**API キー不要。オプションのローカル Ollama LLM。Python 標準ライブラリのみ。**

DendroPivot は単一の検索を、ガイド付き探索パスに変換します。各ラウンドで、シードクエリは 5 つの*フォーカス*再定式化と 5 つの*隣接*トピックに分岐します。読んだ内容がツリーを強化し、どの結果も新しいルートになれます。ターミナルまたはローカルライブ Web ページとして動作し、API キーなしで複数の無料検索インデックスを照会し、[Ollama](https://ollama.com) 経由でローカル LLM を使用でき、Python 標準ライブラリのみを必要とします。

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![ライセンス: MIT](https://img.shields.io/badge/license-MIT-green.svg)](../LICENSE)
[![API キー不要](https://img.shields.io/badge/API%E3%82%AD%E3%83%BC-%E4%B8%8D%E8%A6%81-success)](#検索バックエンド)

[English](../README.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Русский](README.ru.md) · [中文](README.zh.md) · **日本語** · [Português](README.pt.md)

</div>

---

## なぜ DendroPivot？

1 つの検索クエリはトピックの 1 つの角度しか示しません。DendroPivot はクエリを**種**として扱い、5 つの再定式化と 5 つの隣接トピックに展開し、複数の無料検索インデックスに対して実行し、実際に開いたものを使って次のラウンドを誘導します。結果は 10 個のリンクのフラットリストではなく、探索ツリーです。

## ピボット手法

| ステップ | 何が起きるか | なぜ役立つか |
|---|---|---|
| 1. **種** | 初期クエリを入力。 | ツリーのルートを設定。 |
| 2. **分岐** | 5 つのフォーカス角度と 5 つの隣接トピックに展開。 | 1 つのランキングではなく複数の視点。 |
| 3. **読む** | 結果を開くとその語彙が強化される。 | あなたの興味が次のラウンドを誘導。 |
| 4. **成長** | 新しいラウンドが共通の用語でクエリを固定。 | ドメインの核心概念が見えてくる。 |
| 5. **ピボット** | `f` または Shift+クリック：結果が新しいルートに。 | コンテキストを失わずにサブトピックを深掘り。 |
| 6. **戻る** | 履歴が各ツリーを保存；`b`/`n` でナビゲート。 | ブランチを比較していつでも戻れる。 |

## 機能

- **ラウンドごとに 2 列**：フォーカス（5 つの再定式化）+ 隣接（5 つの関連トピック）
- **継続的な充実**：既読の結果が次のラウンドに影響
- **マルチバックエンド検索**：Bing RSS、Marginalia、Yahoo、DDG Lite — ローテーション、フォールバック、クールダウン付き
- **HTML ファースト**：ブラウザでライブツリーを開く；ターミナル外では HTML スナップショットを作成
- **6 言語**：`--lang fr|en|es|it|zh|ru`
- **オプションの Ollama**：LLM クエリ拡張とオンデマンド翻訳
- **標準ライブラリのみ**：`pip install` 不要、Python 3.10+ のどこでも動作

## 要件

| コンポーネント | 要件 |
|---|---|
| Python | **3.10 以上** |
| ネットワーク | 検索バックエンドへのアウトバウンド HTTPS |
| Ollama | オプション、LLM 拡張と翻訳のみ |
| Python パッケージ | なし |

## インストール

```bash
git clone https://github.com/TFD-42/dendropivot-search.git
cd dendropivot-search
python3 websearch.py -q "ローカル言語モデル"
```

## クイックスタート

```bash
# ブラウザでライブ HTML ツリー（ターミナルで実行時のデフォルト）
python3 websearch.py -q "機械学習"

# 1 ラウンドを JSON として
python3 websearch.py -q "機械学習" --rounds 1 --no-ollama --json

# 2 列ターミナルインターフェース
python3 websearch.py -q "機械学習" --tui
```

## 出力モード

| コンテキスト | デフォルト出力 | オーバーライド |
|---|---|---|
| ターミナルから | `http://127.0.0.1:8765/` のライブ HTML ツリー | `--tui`、`--json`、`--text` |
| パイプ/スクリプト（TTY なし） | 現在のディレクトリの HTML スナップショット | `--html-out パス`、`--json` |

## コマンドラインオプション

| オプション | デフォルト | 説明 |
|---|---|---|
| `-q`、`--query テキスト` | プロンプト | 初期シードクエリ |
| `-n`、`--limit N` | `6` | クエリごとの最大結果数 |
| `--interval 秒` | `60` | ラウンド間の遅延 |
| `--rounds N` | `0` | ラウンド数（0 = 無制限） |
| `--lang コード` | 自動 | `fr`、`en`、`es`、`it`、`zh`、`ru` |
| `--no-ollama` | オフ | ヒューリスティック拡張のみ |
| `--tui` | オフ | ターミナルインターフェース |
| `--json` | オフ | stdout に JSON |
| `--text` | オフ | stdout にプレーンテキスト |
| `--html-out パス` | 自動 | スナップショットパス |

## 検索バックエンド

| バックエンド | エンドポイント | 備考 |
|---|---|---|
| `bing-rss` | `bing.com/search?format=rss` | 構造化 RSS |
| `marginalia` | `old-search.marginalia.nu` | 独立インデックス |
| `yahoo` | `search.yahoo.com` | HTML パース |
| `ddg-lite` | `lite.duckduckgo.com/lite/` | POST ベース |

## ライセンス

[MIT ライセンス](../LICENSE) の下でリリース。

---

<div align="center">

[@TFD-42](https://github.com/TFD-42) がメンテナンス · [バグを報告](https://github.com/TFD-42/dendropivot-search/issues/new?template=bug_report.yml)

</div>
