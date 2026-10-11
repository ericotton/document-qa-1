import base64
import hashlib
from pathlib import Path

import streamlit as st
from openai import OpenAI

st.title("📄 文書・画像への質問")
st.write(
    "文書や画像をアップロードして質問できます。"
    "回答後も、これまでのやりとりを踏まえて続けて質問できます。"
)

openai_api_key = st.text_input("OpenAI API Key", type="password")

if not openai_api_key:
    st.info("OpenAI APIキーを入力してください。", icon="🗝️")
    st.stop()

client = OpenAI(api_key=openai_api_key)

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

# ファイルを変更・削除したら、前の会話をリセット
if document_id != st.session_state.document_id:
    st.session_state.chat_history = []
    st.session_state.document_id = document_id

if uploaded_file is None:
    st.info("まず、質問したい文書や画像をアップロードしてください。")
    st.stop()

if uploaded_file.size > 20 * 1024 * 1024:
    st.error("20MB以下のファイルをアップロードしてください。")
    st.stop()

# ファイルをAIに渡すための形式に変換
extension = Path(uploaded_file.name).suffix.lower()

try:
    if extension in [".txt", ".md"]:
        try:
            document = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            document = file_bytes.decode("cp932")

        document_content = {
            "type": "text",
            "text": f"以下は参照する文書の内容です。\n\n{document}",
        }

    elif extension == ".pdf":
        encoded = base64.b64encode(file_bytes).decode("ascii")

        document_content = {
            "type": "file",
            "file": {
                "filename": uploaded_file.name,
                "file_data": f"data:application/pdf;base64,{encoded}",
            },
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
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{encoded}",
            },
        }

except UnicodeDecodeError:
    st.error("文字コードを読み取れません。UTF-8で保存して再度お試しください。")
    st.stop()

# 同じ資料で会話をやり直すボタン
if st.button("会話をリセット"):
    st.session_state.chat_history = []

# これまでの質問と回答を画面に表示
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 回答後も使える質問欄
question = st.chat_input(
    "資料について質問してください。回答への追加質問もできます。"
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

    # 資料は最初の質問に添付し、各リクエストで１回だけ送る
    first_question = conversation[0]["content"]

    messages = [
        {
            "role": "system",
            "content": (
                "あなたは文書・画像についての質問に答えるアシスタントです。"
                "添付資料と、これまでの質問・回答を踏まえて日本語で回答してください。"
                "「それ」「先ほどの回答」などは会話の文脈から解釈してください。"
                "資料にない情報や読み取れない箇所は、推測せず明示してください。"
            ),
        },
        {
            "role": "user",
            "content": [
                document_content,
                {"type": "text", "text": first_question},
            ],
        },
        *conversation[1:],
    ]

    try:
        with st.chat_message("assistant"):
            stream = client.chat.completions.create(
                model="gpt-6.1-sol",
                messages=messages,
                stream=True,
            )

            answer = st.write_stream(stream)

        # 回答が完了したら、今回の質問と回答を履歴に保存
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
