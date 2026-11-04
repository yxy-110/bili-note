from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bilibili_api import video, sync
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
SILICONFLOW_URL = "https://api.siliconflow.cn/v1/chat/completions"

class BiliRequest(BaseModel):
    bv: str

def extract_bv(url: str):
    if url.startswith("BV"):
        return url
    import re
    res = re.search(r"BV([a-zA-Z0-9]+)", url)
    if res:
        return "BV" + res.group(1)
    return None

async def get_subtitle(bv: str):
    v = video.Video(bvid=bv)
    info = await v.get_info()
    subtitles = info.get("subtitle", {}).get("list", [])
    if not subtitles:
        raise HTTPException(status_code=400, detail="该视频没有自带CC字幕，无法提取")
    sub_url = subtitles[0]["subtitle_url"]
    sub_resp = requests.get(sub_url)
    sub_data = sub_resp.json()
    lines = []
    for item in sub_data["body"]:
        start = round(item["from"], 1)
        end = round(item["to"], 1)
        lines.append(f"[{start}s - {end}s] {item['content']}")
    return "\n".join(lines)

def summary_text(sub_text: str):
    prompt = f"""
你是笔记整理助手，根据下面带时间戳的视频字幕，整理结构化学习笔记：
1. 核心一句话总结
2. 分点重点内容，带上对应时间戳
3. 最后提炼可直接复制的摘要
字幕内容：
{sub_text}
"""
    payload = {
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.4
    }
    headers = {
        "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
        "Content-Type": "application/json"
    }
    r = requests.post(SILICONFLOW_URL, json=payload, headers=headers)
    return r.json()["choices"][0]["message"]["content"]

@app.post("/api/get_note")
async def get_note(req: BiliRequest):
    if not SILICONFLOW_API_KEY:
        raise HTTPException(status_code=500, detail="未配置硅基流动密钥")
    bv = extract_bv(req.bv)
    if not bv:
        raise HTTPException(status_code=400, detail="解析BV链接失败")
    sub_text = await get_subtitle(bv)
    note = summary_text(sub_text)
    return {"subtitle": sub_text, "note": note}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
