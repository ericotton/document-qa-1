import base64
import hashlib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
from openai import OpenAI


# APIの出典情報を、クリックできるリンクに変換
def format_answer(response):
    paragraphs = []

    for item in response.output:
        if item.type != "message":
            continue

        for part in item.content:
            if part.type == "refusal":
                paragraphs.append(part.refusal)
                continue

            if part.type != "output_text":
                continue

            text = part.text
            citations = [
                annotation
                for annotation in part.annotations
                if annotation.type == "url_citation"
            ]

            # 後ろから置換し、文字位置がずれないようにする
            for citation in sorted(
                citations,
                key=lambda annotation: annotation.start_index,
                reverse=True,
            ):
                link = f" [出典](<{citation.url}>)"
                text = (
                    text[:citation.start_index]
                    + link
                    + text[citation.end_index:]
                )

            paragraphs.append(text)

    return "\n\n".join(paragraphs)


st.title("📄 文書・画像への質問")
st.write(
    "文書や画像とWeb検索を使って質問に回答します。"
    "回答後も、これまでのやりとりを踏まえて続けて質問できます。"
)

# Secretsに保存したAPIキーを自動で読み込む
try:
    openai_api_key = st.secrets["OPENAI_API_KEY"]
except (KeyError, FileNotFoundError):
    st.error("アプリ管理者がSecretsにOPENAI_API_KEYを設定してください。")
    st.stop()

if not isinstance(openai_api_key, str) or not openai_api_key.strip():
    st.error("SecretsのOPENAI_API_KEYに有効なAPIキーを設定してください。")
    st.stop()

client = OpenAI(api_key=openai_api_key.strip())

# 会話履歴を初期化
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "document_id" not in st.session_state:
    st.session_state.document_id = None

uploaded_file = st.file_uploader(
    "ファイルをアップロード（TXT・MD・PDF・PNG・JPG・JPEG・WebP）",
    type=["txt", "md", "pdf", "png", "jpg", "jpeg", "webp"],
    help="このアプリでは、１ファイル20MBまでに制限しています。",
)

# ファイルの変更を検出
file_bytes = uploaded_file.getvalue() if uploaded_file else None

document_id = (
    (
        uploaded_file.name,
        hashlib.sha256(file_bytes).hexdigest(),
    )
    if uploaded_file
    else None
)

# ファイルを変更・削除したら会話をリセット
if document_id != st.session_state.document_id:
    st.session_state.chat_history = []
    st.session_state.document_id = document_id

if uploaded_file is None:
    st.info("まず、質問したい文書や画像をアップロードしてください。")
    st.stop()

if uploaded_file.size > 20 * 1024 * 1024:
    st.error("20MB以下のファイルをアップロードしてください。")
    st.stop()

# Responses API用の形式に変換
extension = Path(uploaded_file.name).suffix.lower()

try:
    if extension in [".txt", ".md"]:
        try:
            document = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            document = file_bytes.decode("cp932")

        document_content = {
            "type": "input_text",
            "text": f"以下は参照する文書の内容です。\n\n{document}",
        }

    elif extension == ".pdf":
        encoded = base64.b64encode(file_bytes).decode("ascii")

        document_content = {
            "type": "input_file",
            "filename": uploaded_file.name,
            "file_data": f"data:application/pdf;base64,{encoded}",
        }

    else:
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }
        mime_type = mime_types[extension]
        encoded = base64.b64encode(file_bytes).decode("ascii")

        document_content = {
            "type": "input_image",
            "image_url": f"data:{mime_type};base64,{encoded}",
        }

except UnicodeDecodeError:
    st.error("文字コードを読み取れません。UTF-8で保存して再度お試しください。")
    st.stop()

# 同じ資料で会話をやり直すボタン
if st.button("会話をリセット"):
    st.session_state.chat_history = []

# 過去の質問・回答を表示
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 回答後も使える質問欄
question = st.chat_input(
    "資料について質問してください。最新情報の確認や追加質問もできます。"
)

if question and question.strip():
    question = question.strip()

    with st.chat_message("user"):
        st.markdown(question)

    # 過去の会話と今回の質問をまとめる
    conversation = [
        *st.session_state.chat_history,
        {"role": "user", "content": question},
    ]

    # 資料は各リクエストに１回だけ添付
    messages = [
        {
            "role": "user",
            "content": [
                document_content,
                {
                    "type": "input_text",
                    "text": conversation[0]["content"],
                },
            ],
        },
        *conversation[1:],
    ]

    # 日本時間の現在日時を自動取得
    now = datetime.now(ZoneInfo("Asia/Tokyo")).strftime(
        "%Y年%m月%d日 %H:%M（日本時間）"
    )

    instructions = (
        "あなたは文書・画像とWeb検索を使って質問に答えるアシスタントです。"
        f"現在日時は{now}です。"
        "添付資料とこれまでの会話を踏まえ、日本語で回答してください。"
        "質問に関連する情報をWeb検索で確認してください。"
        "最新情報を求められた場合は、現在日時までに公開された情報を調べ、"
        "公開日と出来事の日付を確認してください。"
        "できるだけ公式サイトなどの一次情報を優先してください。"
        "添付資料の記載とWeb検索で得た情報を区別し、"
        "相違があればその内容と時点を説明してください。"
        "Web情報には出典を付けてください。"
        "確認できない情報や資料の読み取れない箇所は推測せず明示してください。"
        "検索していない情報を、検索で確認したと述べないでください。"
        "「それ」「先ほどの回答」などは会話の文脈から解釈してください。"
    )

    try:
        with st.chat_message("assistant"):
            with st.spinner("Web検索で情報を確認し、回答を作成しています…"):
                response = client.responses.create(
                    model="gpt-6.1-sol",
                    instructions=instructions,
                    input=messages,
                    tools=[
                        {
                            "type": "web_search",
                            "external_web_access": True,
                        }
                    ],
                    # 質問ごとにWeb検索を実行
                    tool_choice="required",
                    store=False,
                )

                if response.status != "completed":
                    raise RuntimeError(
                        "回答が完了しませんでした。質問を短くして再度お試しください。"
                    )

                answer = format_answer(response)

                if not answer.strip():
                    raise RuntimeError(
                        "回答を取得できませんでした。再度お試しください。"
                    )

            st.markdown(answer)

        # 完了した質問・回答を保存
        st.session_state.chat_history.extend([
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ])

    except Exception as e:
        st.error(f"処理中にエラーが発生しました：{e}")
        st.info(
            "今回の質問・回答は履歴に保存されていません。"
            "質問欄からもう一度送信してください。"
        )
