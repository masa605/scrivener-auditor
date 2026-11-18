"""
Scrivener × Gemini 論理監査官 (Story Logic Auditor)

引き算の美学と責任の境界線（HOTL: Human-On-The-Loop）を徹底した、
長編小説の構造化プロットに対する静的解析・論理監査Webアプリケーション。
"""

import hashlib
import json
import os
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

# ==========================================
# 1. 確定的処理（Deterministic Processing）
#    Python標準ライブラリのみで100%正確に実行
# ==========================================


# 除外対象のルートフォルダ名（小文字正規化で判定）
EXCLUDED_ROOT_TITLES = {
    "trash",
    "ゴミ箱",
    "template sheets",
    "novel format",
}


def count_outline_nodes(element: ET.Element) -> int:
    """要素自身および配下のすべてのoutlineタグの総数を再帰的にカウントする。"""
    count = 1
    for child in element:
        tag_name = child.tag.split("}")[-1].lower()
        if tag_name == "outline":
            count += count_outline_nodes(child)
    return count


def parse_scrivener_opml(xml_bytes: bytes) -> Tuple[List[Dict[str, Any]], int]:
    """Scrivenerから出力されたOPML(XML)をパースし、

    章・シーンの階層構造、インデント深度、シノプシス/本文を抽出して
    クリーンな構造化リスト（JSON互換）に変換する。

    Trash, Template Sheets, Novel Format などの不要なルートノードは
    配下を含めて完全に除外する。
    戻り値: (有効ノードリスト, 除外されたノード総数)
    """
    # UTF-8 BOM対応デコード
    text = xml_bytes.decode("utf-8-sig", errors="replace")
    root = ET.fromstring(text)

    # <body> タグの探索（名前空間無視）
    body = None
    for child in root:
        tag_name = child.tag.split("}")[-1].lower()
        if tag_name == "body":
            body = child
            break

    container = body if body is not None else root

    parsed_nodes: List[Dict[str, Any]] = []
    excluded_count = 0

    def traverse(element: ET.Element, current_path: List[str], depth: int):
        nonlocal excluded_count
        for child in element:
            tag_name = child.tag.split("}")[-1].lower()
            if tag_name == "outline":
                title = (
                    child.attrib.get("text")
                    or child.attrib.get("title")
                    or "（無題）"
                ).strip()

                # ルートレベル（depth == 1）でのノイズ除外フィルタリング
                if depth == 1 and title.lower() in EXCLUDED_ROOT_TITLES:
                    excluded_count += count_outline_nodes(child)
                    continue

                # ScrivenerのOPML出力におけるシノプシス/本文は主に '_note' 属性
                synopsis = (
                    child.attrib.get("_note")
                    or child.attrib.get("description")
                    or ""
                ).strip()

                new_path = current_path + [title]
                path_str = " > ".join(new_path)

                node_index = len(parsed_nodes) + 1
                parsed_nodes.append(
                    {
                        "index": node_index,
                        "depth": depth,
                        "path": path_str,
                        "title": title,
                        "synopsis_or_text": synopsis,
                    }
                )

                # 子ノードを再帰走査
                traverse(child, new_path, depth + 1)

    traverse(container, [], depth=1)
    return parsed_nodes, excluded_count


# ==========================================
# 2. 確率的処理（Gemini API連携）
#    構造化データに対する冷酷な論理監査
# ==========================================


def build_audit_prompt(
    nodes: List[Dict[str, Any]],
    chk_info: bool,
    chk_timeline: bool,
    chk_deadlock: bool,
) -> Tuple[str, str]:
    """監査プロンプト（システム指示およびユーザー入力）を生成する。"""
    audit_focus_items = []
    if chk_info:
        audit_focus_items.append(
            "- **情報の先回りバグ**:\n"
            "  登場人物が作中の時系列上、まだ知り得ない事実・他者の内心・未公開の固有名詞・未観測の事件などを、"
            "  なぜか知っている前提で会話・行動・思考している論理的欠陥。"
        )
    if chk_timeline:
        audit_focus_items.append(
            "- **タイムライン・物理移動の破綻**:\n"
            "  先行シーンと後続シーン間での経過時間の不整合、地理的距離に対する移動速度・所要時間の無視、"
            "  昼夜・天候の唐突な矛盾、およびハードSF・工学・物理設定上の破綻。"
        )
    if chk_deadlock:
        audit_focus_items.append(
            "- **設定・伏線のデッドロック**:\n"
            "  作中世界の前提ルール・技術仕様との自己矛盾、放置された回収不能な伏線、"
            "  登場人物の物理的動線や生死・負傷状態の不整合（A地点にいるはずの人物が説明なくB地点に現れる等）。"
        )

    focus_text = "\n".join(audit_focus_items)

    system_instruction = f"""あなたは冷酷かつ極めて優秀なソフトウェアコードレビュアーであり、長編小説の物語論理監査官です。
お世辞、修辞的賞賛、感想、励ましは一切不要です。無駄口を完全に排除し、冷徹な静的解析レポートのみを出力してください。

【任務】
提供された作品の構造化プロットデータ（JSON）を全編にわたって静的解析（Static Analysis）し、
論理的バグ、時間・空間の破綻、情報の先回り、設定の矛盾を容赦なく検出・告発してください。

【重点監査項目】
{focus_text}

【出力形式（厳守）】
以下の構造化Markdown形式で出力してください。

# 物語論理監査レポート

## 1. 監査サマリー
- **解析ノード総数**: (数値) 件
- **検出バグ総数**: CRITICAL: (数値) 件 / WARNING: (数値) 件 / INFO: (数値) 件
- **総合論理健全度**: (1行で冷徹に判定)

## 2. 検出された論理バグ一覧
（問題が検出されなかった場合は「論理的矛盾は検出されませんでした。」と明記してください）

### 指摘 [連番]: [CRITICAL | WARNING | INFO] (バグの簡潔な要約)
- **該当箇所**: (階層パス > シーンタイトル / index番号)
- **バグの種類**: (情報の先回り / タイムライン破綻 / 設定デッドロック)
- **冷酷な指摘内容**: (なぜ矛盾しているのか、どの先行/後続シーン[index番号とタイトル]のどの記述と衝突しているのかを、客観的証拠を挙げて冷酷に論証)
- **修正の方向性**: (著者が自ら判断・修正するための簡潔で論理的な修正案)

## 3. 次のアクション（HOTLタスクリスト）
著者（人間）がScrivener上で手作業で確認・修正すべき具体的ToDoチェックリスト：
- [ ] (具体的な確認・修正タスク)
"""

    user_content = f"""以下は解析対象となる長編小説の全編構造化データ（JSON）です。
全編を静的解析し、システム指示に従って論理監査レポートを出力してください。

```json
{json.dumps(nodes, ensure_ascii=False, indent=2)}
```
"""
    return system_instruction, user_content


def execute_gemini_audit(
    api_key: str,
    system_instruction: str,
    user_content: str,
    model_name: str = "gemini-3.1-pro-preview",
) -> str:
    """google-genai SDKを用いてGemini APIを呼び出す。"""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError(
            "google-genai パッケージがインストールされていません。"
            "ターミナルで `pip install google-genai` を実行してください。"
        )

    # APIクライアント初期化
    client = genai.Client(api_key=api_key)

    # 生成呼び出し（論理的・決定的な解析のため temperature を低く設定）
    response = client.models.generate_content(
        model=model_name,
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
        ),
    )

    if not response.text:
        raise RuntimeError("Gemini APIからの応答が空でした。")

    return response.text


# ==========================================
# 3. Streamlit 1画面 UI（Single-Page Pipeline）
# ==========================================


def main():
    st.set_page_config(
        page_title="Scrivener × Gemini 論理監査官",
        page_icon="⚖️",
        layout="wide",
    )

    # タイトル・哲学ヘッダー
    st.title("⚖️ Scrivener × Gemini 論理監査官")
    st.caption(
        "**引き算の美学 × 責任の境界線（HOTL）** ｜ "
        "ScrivenerのOPMLアウトラインから、物語の論理的バグ・矛盾・設定の破綻を冷酷に摘出する単機能静的解析パイプライン"
    )

    # --- サイドバー: APIキーと環境設定 ---
    env_api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    with st.sidebar:
        st.header("⚙️ 設定")
        
        # 画面上でいつでもAPIキーを確認・再入力・上書き可能にする
        input_key = st.text_input(
            "Gemini API Key",
            value=env_api_key,
            type="password",
            placeholder="AIzaSy...",
            help="Google AI Studio (https://aistudio.google.com/apikey) で取得したAPIキーを入力してください。",
        ).strip().strip("'\"")

        if input_key:
            if input_key == env_api_key and env_api_key:
                st.success("✅ 環境変数のAPIキーを適用中")
            else:
                st.info("🔑 手動入力されたAPIキーを適用中")
            api_key = input_key
        else:
            st.warning("⚠️ APIキーが未入力です")
            api_key = ""

        st.markdown("---")
        model_name = st.selectbox(
            "監査モデル",
            options=["gemini-3.1-pro-preview", "gemini-2.5-flash", "カスタム指定"],
            index=0,
            help="Google公式推奨の最新モデル `gemini-3.1-pro-preview` を使用します。",
        )
        if model_name == "カスタム指定":
            model_name = st.text_input("モデル名を入力", value="gemini-3.1-pro-preview").strip()

        st.markdown("**設計思想**:")
        st.markdown("- 確定的処理（Python標準XMLパース）")
        st.markdown("- 確率的処理（Gemini長文論理推論）")
        st.markdown("- 原稿ファイルの保護（HOTL: 読取専用）")

    # --- Step 1: ファイルアップロード ---
    st.subheader("1. OPMLファイルのアップロード")
    uploaded_file = st.file_uploader(
        "Scrivenerから書き出した `.opml` または `.xml` ファイルをドロップしてください",
        type=["opml", "xml"],
        help="Scrivenerメニューの [File] > [Export] > [OPML File...] から書き出したファイルを選択します。",
    )

    if not uploaded_file:
        st.info(
            "👆 Scrivenerで `File > Export > OPML File...` を実行し、生成されたファイルをアップロードしてください。\n\n"
            "※ 本ツールは `.scriv` パッケージを一切書き換えません。安全に監査レポートと構造化JSONのみを出力します。"
        )
        return

    # ファイルのバイナリ読み込みとハッシュ算出（セッション状態の整合性管理用）
    file_bytes = uploaded_file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    if st.session_state.get("current_file_hash") != file_hash:
        st.session_state["current_file_hash"] = file_hash
        st.session_state["parsed_nodes"] = None
        st.session_state["excluded_count"] = 0
        st.session_state["audit_report"] = None

    # --- Step 2: 確定的データ変換（Python標準 XMLパース） ---
    if st.session_state.get("parsed_nodes") is None:
        try:
            nodes, excluded_count = parse_scrivener_opml(file_bytes)
            st.session_state["parsed_nodes"] = nodes
            st.session_state["excluded_count"] = excluded_count
        except ET.ParseError as e:
            st.error(f"❌ OPMLファイルのXML解析に失敗しました: {e}")
            return
        except Exception as e:
            st.error(f"❌ 予期しないエラーが発生しました: {e}")
            return

    nodes: List[Dict[str, Any]] = st.session_state["parsed_nodes"]
    excluded_count: int = st.session_state.get("excluded_count", 0)

    if not nodes:
        st.warning("⚠️ OPMLファイル内に有効な `<outline>` 項目が見つかりませんでした。書き出し設定をご確認ください。")
        return

    # 構造確認（折りたたみ表示）
    st.subheader("2. 構造化データの確認（確定的処理）")
    if excluded_count > 0:
        st.success(
            f"✅ 解析成功: 有効ノード **{len(nodes)}** 件を抽出しました"
            f"（Trash等の不要ノード **{excluded_count}** 件を除外）"
        )
    else:
        st.success(f"✅ 解析成功: 全 **{len(nodes)}** 件の構成ノード（章・シーン）を抽出しました。")

    with st.expander("🔍 抽出されたアウトライン構造を確認する（クリックで開閉）", expanded=False):
        for node in nodes:
            indent = "　" * (node["depth"] - 1)
            prefix = "📁" if node["depth"] <= 2 else "📄"
            note_preview = (
                f" — *{node['synopsis_or_text'][:60]}...*"
                if node["synopsis_or_text"]
                else " *(シノプシス未記入)*"
            )
            st.markdown(f"`#{node['index']:02d}` {indent} {prefix} **{node['title']}** {note_preview}")

    # --- Step 3: 監査オプションと実行 ---
    st.subheader("3. 冷酷な論理監査（Gemini API連携）")

    col1, col2, col3 = st.columns(3)
    with col1:
        chk_info = st.checkbox(
            "情報の先回りバグ",
            value=True,
            help="登場人物が知り得ない事実・名前を前提に行動・発言している箇所を検出",
        )
    with col2:
        chk_timeline = st.checkbox(
            "タイムライン・物理移動の破綻",
            value=True,
            help="時間経過、地理的移動時間、物理・工学設定の矛盾を検出",
        )
    with col3:
        chk_deadlock = st.checkbox(
            "設定・伏線のデッドロック",
            value=True,
            help="世界観ルールとの衝突、未回収伏線、人物動線の破綻を検出",
        )

    if not (chk_info or chk_timeline or chk_deadlock):
        st.warning("⚠️ 少なくとも1つの監査オプションを選択してください。")
        return

    execute_btn = st.button("🚨 冷酷な論理監査を実行する", type="primary", use_container_width=True)

    if execute_btn:
        if not api_key:
            st.error("❌ Gemini API Key が設定されていません。サイドバーから入力するか、環境変数 `GEMINI_API_KEY` を設定してください。")
            return

        system_instruction, user_content = build_audit_prompt(
            nodes=nodes,
            chk_info=chk_info,
            chk_timeline=chk_timeline,
            chk_deadlock=chk_deadlock,
        )

        with st.spinner("⚡ 冷酷な論理監査官が全編プロットを静的解析中...（矛盾・破綻を洗い出しています）"):
            try:
                report = execute_gemini_audit(
                    api_key=api_key,
                    system_instruction=system_instruction,
                    user_content=user_content,
                    model_name=model_name,
                )
                st.session_state["audit_report"] = report
                st.toast("論理監査が完了しました！", icon="✅")
            except Exception as e:
                st.error(f"❌ 監査実行中にエラーが発生しました: {e}")
                return

    # --- Step 4: レポート & 持ち帰りセクション（HOTL） ---
    audit_report = st.session_state.get("audit_report")
    if audit_report:
        st.divider()
        st.subheader("4. 監査レポート ＆ 持ち帰り（HOTL）")
        st.caption(
            "修正判断と原稿編集は人間（著者）が行います。"
            "`audit_report.md` を Scrivener の `Research` フォルダにドラッグ＆ドロップし、"
            "スプリット画面で照合しながら原稿を推敲してください。"
        )

        # 2つのダウンロードボタン
        json_data = json.dumps(nodes, ensure_ascii=False, indent=2)
        down_col1, down_col2 = st.columns(2)

        with down_col1:
            st.download_button(
                label="📥 監査レポートをダウンロード (`audit_report.md`)",
                data=audit_report,
                file_name="audit_report.md",
                mime="text/markdown",
                use_container_width=True,
            )

        with down_col2:
            st.download_button(
                label="📥 構造化データをダウンロード (`parsed_structure.json`)",
                data=json_data,
                file_name="parsed_structure.json",
                mime="application/json",
                use_container_width=True,
            )

        # 画面レンダリング表示
        st.markdown("---")
        st.markdown(audit_report)


if __name__ == "__main__":
    main()
