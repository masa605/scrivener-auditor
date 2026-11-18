# Scrivener × Gemini 論理監査官 (Story Logic Auditor)

長編小説（ハードSF、ミステリー、ファンタジー等）の執筆環境である **Scrivener** と **Gemini API** を接続し、作品全体の構造化プロットから論理的バグ・時間空間の破綻・設定の穴を容赦なく摘出する、最小限で堅牢なローカルWebアプリケーションです。

---

## 開発哲学と設計思想

### 1. 単機能MVPへの徹底的な引き算
- タブ切り替えや豪華なダッシュボードを排除。
- 画面は **「OPMLアップロード → 構造確認 → 冷酷な論理監査実行 → レポート＆タスク出力」** の1画面パイプラインのみで完結。
- 余計なアウトライン自動生成や、Scrivenerプロジェクトへの自動書き込み機能は一切持ちません。

### 2. 確定的処理と確率的処理の厳密な分離
- **確定的処理（Python標準 `xml.etree.ElementTree`）**:
  Scrivenerが出力したOPML（XML）ファイルを100%正確にパース。章・シーンの階層深度（Depth）、親子関係パス（Path）、タイトル、シノプシス（`_note`）を抽出して構造化JSONへ変換します。外部ライブラリ（pandas等）は使わず、純粋なPython標準機能のみで完結します。
- **確率的処理（Gemini API / `gemini-3.1-pro-preview`）**:
  長大なコンテキストウィンドウと高度な論理推論力を備えたGoogle最新のフラグシップモデル `gemini-3.1-pro-preview` が、構造化された全編プロットに対して「冷酷なコードレビュー」に徹した静的解析を実行します。

### 3. Scrivenerデータの絶対保護（HOTL: Human-On-The-Loop）
- 原稿実体である `.scriv` パッケージ内部のファイルを本アプリが直接操作・書き換えることは絶対にありません。
- AIの役割は「監査レポートの出力」に限定され、修正の判断および原稿の編集は必ず人間（著者）がScrivener上で手作業で行います。

---

## 0円スタック構成・動作コスト目安

- **フロントエンド / バックエンド**: Streamlit（オープンソース）
- **AI推論**: Google Gemini API (`gemini-3.1-pro-preview` / `gemini-2.5-flash`)
- **データ解析**: Python 3.10+ 標準ライブラリ (`xml.etree.ElementTree`, `json`, `hashlib`, `os`)
- **推論コスト目安**:
  - Google AI Studioの無料枠（Free Tier）の範囲内であれば **完全0円** で運用可能。
  - 有料枠（従量課金）を使用した場合でも、長編小説1編（約80〜100ノードの全編構造化プロット）の論理監査1回あたり **約10〜15円（実測検証例: 81ノード監査で約13円/回）** と極めて経済的に実行可能です。

---

## セットアップと起動手順

### 1. 前提条件
- Python 3.10 以上がインストールされていること。
- [Google AI Studio](https://aistudio.google.com/) でGemini APIキーを取得していること。

### 2. リポジトリのクローンと環境構築
ターミナルを開き、以下の手順でセットアップします：

```bash
# リポジトリのクローン（またはダウンロード）
git clone https://github.com/<your-username>/scrivener-auditor.git
cd scrivener-auditor

# 仮想環境の作成
python3 -m venv .venv

# 仮想環境の有効化 (macOS / Linux)
source .venv/bin/activate
# Windows の場合: .venv\Scripts\activate

# 必要パッケージのインストール（streamlit と google-genai のみ）
pip install -r requirements.txt
```

### 3. APIキーの設定とアプリケーション起動
環境変数に設定して起動するか、起動後のブラウザ画面（サイドバー）で直接入力できます。

**方法A: 環境変数ファイル（.env）または export で設定して起動（推奨）**
```bash
# .env.example から .env を作成
cp .env.example .env
# .env ファイル内の GEMINI_API_KEY にご自身のAPIキーを記入

# またはターミナルで直接 export
export GEMINI_API_KEY="AIzaSy..."

# アプリケーション起動
streamlit run app.py
```

**方法B: 設定なしで直接起動**
```bash
streamlit run app.py
```
起動後、ブラウザ画面左側のサイドバー「Gemini API Key」欄にAPIキーを直接入力してください。

ブラウザで `http://localhost:8501` が自動的に開きます。

---

## Scrivener側でのOPML書き出し手順

本アプリは、Scrivenerの標準機能であるOPMLエクスポートファイルを入力とします。

1. **Scrivenerでプロジェクトを開く**
   - バインダー（Binder）上で、監査対象としたいフォルダ（例: `Draft` または `原稿` 全体）を選択します。
2. **OPML形式で書き出す**
   - メニューバーから **[File] > [Export] > [OPML File...]** を選択します。
3. **書き出しオプションの選択**
   - ダイアログで以下のいずれかを選択します：
     - **Titles and Synopses**（推奨: コルクボードのシノプシスを中心にプロット監査する場合）
     - **Titles and Text**（シーン本文を含めてより詳細に論理監査する場合）
4. **保存した `.opml` ファイルを本アプリにドラッグ＆ドロップ**

---

## HOTL（執筆・推敲）ワークフロー

1. **アップロードと構造確認**:
   - アップロード後、「2. 構造化データの確認」のアコーディオンを展開し、階層構造やシノプシスが正しく抽出されているか確認します。
2. **監査オプションの指定**:
   - 重点監査対象を選択（デフォルトは全選択）：
     - **情報の先回りバグ**: 登場人物が知り得ないはずの事実を前提に動いていないか
     - **タイムライン・物理移動の破綻**: 時間経過、移動速度、SF・工学設定の矛盾
     - **設定・伏線のデッドロック**: 世界観ルール違反、放置された伏線、人物動線の矛盾
3. **冷酷な論理監査の実行**:
   - 「冷酷な論理監査を実行する」ボタンを押下。Gemini 3.1 Pro Preview（または選択したモデル）による静的解析が開始されます。
4. **レポートの持ち帰りと推敲**:
   - 出力された **`audit_report.md`** をダウンロードします。
   - Scrivenerのバインダー内にある **`Research`（リサーチ）** フォルダに `audit_report.md` をドラッグ＆ドロップしてインポートします。
   - Scrivenerを **左右2分割（スプリット画面）** にし、左に `audit_report.md` の指摘タスクリスト、右に対象シーンの原稿を開いて、著者の手で確実に改稿を進めます。
