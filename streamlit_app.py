import base64
from pathlib import Path

import streamlit as st
from openai import OpenAI

st.title("📄 文書・画像への質問")
st.write("文書や画像をアップロードして、その内容について質問できます。")

openai_api_key = st.text_input("OpenAI API Key", type="password")

if not openai_api_key:
    st.info("OpenAI APIキーを入力してください。", icon="🗝️")
    st.stop()

client = OpenAI(api_key=openai_api_key)

# アップロードできる種類を追加
uploaded_file = st.file_uploader(
    "ファイルをアップロード（TXT・MD・PDF・PNG・JPG・JPEG・WebP）",
    type=["txt", "md", "pdf", "png", "jpg", "jpeg", "webp"],
    help="このアプリでは、１ファイル20MBまでに制限しています。",
)

question = st.text_area(
    "ファイルについて質問してください。",
    placeholder="内容を日本語で要約してください。",
    disabled=uploaded_file is None,
)

# ボタンを押したときだけ、AIへ送信
if st.button(
    "回答を生成",
    disabled=uploaded_file is None or not question.strip(),
):
    if uploaded_file.size > 20 * 1024 * 1024:
        st.error("20MB以下のファイルをアップロードしてください。")
        st.stop()

    file_bytes = uploaded_file.getvalue()
    extension = Path(uploaded_file.name).suffix.lower()

    try:
        content = []

        # TXT・MD：文字として読み込む
        if extension in [".txt", ".md"]:
            try:
                document = file_bytes.decode("utf-8-sig")
            except UnicodeDecodeError:
                document = file_bytes.decode("cp932")

            content.append({
                "type": "text",
                "text": f"以下は文書の内容です。\n\n{document}",
            })

        # PDF：PDFとしてAIへ渡す
        elif extension == ".pdf":
            encoded = base64.b64encode(file_bytes).decode("ascii")

            content.append({
                "type": "file",
                "file": {
                    "filename": uploaded_file.name,
                    "file_data": f"data:application/pdf;base64,{encoded}",
                },
            })

        # 画像：画像としてAIへ渡す
        else:
            mime_types = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
            }
            mime_type = mime_types[extension]
            encoded = base64.b64encode(file_bytes).decode("ascii")

            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{encoded}",
                },
            })

        # 質問を追加
        content.append({
            "type": "text",
            "text": question.strip(),
        })

        # PDF・画像に対応するモデルで回答
        stream = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "添付された文書や画像に基づいて、日本語で回答してください。"
                        "読み取れない箇所や資料にない情報は、推測せず明示してください。"
                    ),
                },
                {
                    "role": "user",
                    "content": content,
                },
            ],
            stream=True,
        )

        st.write_stream(stream)

    except UnicodeDecodeError:
        st.error("文字コードを読み取れません。UTF-8で保存して再度お試しください。")
    except Exception as e:
        st.error(f"処理中にエラーが発生しました：{e}")
