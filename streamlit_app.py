"""
美好生活文案生成器 — Streamlit 版
======================================
从 Dify 工作流 "小红书风格文案" 转换而来
"""

import streamlit as st
import requests
import base64
import json
import os
from PIL import Image
from io import BytesIO

st.set_page_config(page_title="美好生活文案", page_icon="✨", layout="centered")

XHS_SYSTEM_PROMPT = """你是专业小红书爆款文案创作师，严格按照用户输入内容（文字/图片描述）产出适配小红书平台的笔记文案，遵循以下全部规则：
1. 整体风格：亲切生活化、口语化，像闺蜜分享，拒绝生硬广告腔；情绪自然，轻松有感染力
2. 结构固定四段式：
① 吸睛开头：用反问、共鸣、感叹句抓眼球，控制1-2行；
② 核心内容：细致拆解主体亮点、体验、细节；
③ 走心小结/小贴士：实用总结、避坑提醒、个人真实感受；
④ 精准标签：文末带上5-8个相关热门#话题标签
3. 排版规范：段落简短分行，多用emoji点缀；
4. 字数控制：整体正文300字以内；
5. 禁止：夸大虚假宣传、违规敏感话术。"""

API_KEY = st.secrets.get("SILICONFLOW_API_KEY", os.environ.get("SILICONFLOW_API_KEY", ""))

# --- 会话状态（存压缩后的图片数据，避免 Streamlit 重跑时丢失） ---
if "compressed_img_b64" not in st.session_state:
    st.session_state.compressed_img_b64 = None
if "compressed_img_size" not in st.session_state:
    st.session_state.compressed_img_size = 0
if "compressed_img_name" not in st.session_state:
    st.session_state.compressed_img_name = ""

st.title("✨ 美好生活文案")
st.caption("🚀 上传图片 + 描述，AI 自动生成美好生活文案")

if not API_KEY:
    st.error("⚠️ 未配置 SILICONFLOW_API_KEY")
    st.stop()

# --- 侧边栏 ---
with st.sidebar:
    model = st.selectbox("模型", [
        "Pro/moonshotai/Kimi-K2.5",
    ], format_func=lambda x: "Kimi K2.5 🌟")
    temperature = st.slider("创意程度", 0.1, 1.5, 0.7, 0.1)

# --- 图片上传 + 立即压缩存入 session_state ---
uploaded_file = st.file_uploader("📸 上传图片", type=["jpg", "jpeg", "png", "webp", "gif"])

if uploaded_file is not None:
    # 读取原始数据
    raw = uploaded_file.getvalue()
    # 用 PIL 打开并压缩到最长边 800px
    img = Image.open(BytesIO(raw))
    img.thumbnail((800, 800), Image.LANCZOS)
    # 转 JPEG 质量 85
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    compressed_bytes = buf.getvalue()
    # 存入 session_state
    st.session_state.compressed_img_b64 = base64.b64encode(compressed_bytes).decode("utf-8")
    st.session_state.compressed_img_size = len(compressed_bytes)
    st.session_state.compressed_img_name = uploaded_file.name

    # 显示预览（用压缩后的数据）
    preview_img = Image.open(BytesIO(compressed_bytes))
    preview_img.thumbnail((400, 400), Image.LANCZOS)
    st.image(preview_img, width=300)
    st.caption(f"✅ {uploaded_file.name} (压缩后 {len(compressed_bytes)//1024}KB)")
elif st.session_state.compressed_img_b64 is not None:
    # 用户点了"清除文件"按钮，清理缓存
    st.session_state.compressed_img_b64 = None
    st.session_state.compressed_img_size = 0
    st.session_state.compressed_img_name = ""

# --- 文字输入 ---
user_text = st.text_area("💬 描述（可选，不填则 AI 自动识别图片）",
    placeholder="例：帮我写一篇推荐文案",
    height=80)

# --- 生成按钮 ---
if st.button("🚀 生成文案", type="primary", use_container_width=True):
    has_image = st.session_state.compressed_img_b64 is not None

    if not has_image and not user_text.strip():
        st.warning("请上传图片或输入描述～")
        st.stop()

    # 1. 状态提示
    if has_image:
        st.info(f"📤 已发送图片 ({st.session_state.compressed_img_size//1024}KB) + 文字到 **{model}**，正在生成...")
    else:
        st.info(f"📤 已发送文字到 **{model}**，正在生成...")

    # 2. 构建请求
    if has_image:
        content = [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{st.session_state.compressed_img_b64}"}},
            {"type": "text", "text": user_text or "请根据这张图片创作一篇小红书风格的文案，详细描述图片中的内容。"},
        ]
    else:
        content = user_text or "请创作一篇小红书风格的文案。"

    messages = [
        {"role": "system", "content": XHS_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 4096,
        "stream": True,
    }

    # 3. 流式显示结果
    result_area = st.empty()
    full_text = ""
    has_content = False

    try:
        resp = requests.post(
            "https://api.siliconflow.cn/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            stream=True,
            timeout=120,
        )
        resp.raise_for_status()

        for line in resp.iter_lines():
            if line:
                line = line.decode("utf-8", errors="replace")
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta_content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if delta_content:
                            has_content = True
                            full_text += delta_content
                            result_area.markdown(full_text + "▌")
                    except json.JSONDecodeError:
                        continue

    except requests.exceptions.HTTPError as e:
        err_detail = ""
        try:
            err_detail = resp.json().get("message", resp.text[:300])
        except:
            err_detail = resp.text[:300]
        st.error(f"❌ API 错误 ({resp.status_code}): {err_detail}")
    except Exception as e:
        st.error(f"❌ 错误: {str(e)}")

    # 4. 完成
    if has_content:
        st.success("✅ 生成完成！")
        result_area.markdown(full_text)

        st.divider()
        st.markdown("**📋 复制文案**")
        st.code(full_text, language="text", wrap_lines=True)
    elif not full_text:
        st.warning("⚠️ 模型未返回内容，请换个模型试试")
