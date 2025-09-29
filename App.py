import os
import json
import tempfile
import asyncio
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from gtts import gTTS

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def _extract_text_from_transcription(resp):
    try:
        return getattr(resp, "text", None) or resp.get("text")
    except Exception:
        try:
            return str(resp)
        except Exception:
            return ""

def _extract_text_from_chat(resp):
    try:
        return resp.choices[0].message.content
    except Exception:
        try:
            return resp["choices"][0]["message"]["content"]
        except Exception:
            try:
                return getattr(resp, "text", None) or resp.get("text")
            except Exception:
                return ""

async def _transcribe_file(path):
    def sync(path):
        with open(path, "rb") as f:
            return client.audio.transcriptions.create(file=f, model="whisper-large-v3")
    return await asyncio.to_thread(sync, path)

async def _chat_completion(history):
    def sync(history):
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        return client.chat.completions.create(model="llama-3.1-8b-instant", messages=messages)
    return await asyncio.to_thread(sync, history)

async def _tts_bytes(text):
    def sync(text, out_path):
        t = gTTS(text)
        t.save(out_path)
        with open(out_path, "rb") as f:
            return f.read()
    out_path = tempfile.mktemp(suffix=".mp3")
    try:
        return await asyncio.to_thread(sync, text, out_path)
    finally:
        try:
            os.remove(out_path)
        except Exception:
            pass

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    history = []
    while True:
        try:
            msg = await websocket.receive()
        except Exception:
            break
        if "bytes" in msg:
            data = msg["bytes"]
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".webm")
            try:
                tmp.write(data)
                tmp.flush()
                tmp.close()
                transcription_resp = await _transcribe_file(tmp.name)
            except Exception:
                try:
                    await websocket.send_text(json.dumps({"transcription": "", "response": ""}))
                finally:
                    try:
                        os.remove(tmp.name)
                    except Exception:
                        pass
                continue
            try:
                os.remove(tmp.name)
            except Exception:
                pass
            user_text = _extract_text_from_transcription(transcription_resp) or ""
            history.append({"role": "user", "content": user_text})
            if len(history) > 6:
                history = history[-6:]
            try:
                chat_resp = await _chat_completion(history)
            except Exception:
                await websocket.send_text(json.dumps({"transcription": user_text, "response": ""}))
                continue
            bot_text = _extract_text_from_chat(chat_resp) or ""
            history.append({"role": "assistant", "content": bot_text})
            if len(history) > 6:
                history = history[-6:]
            try:
                audio_bytes = await _tts_bytes(bot_text)
            except Exception:
                audio_bytes = b""
            try:
                await websocket.send_text(json.dumps({"transcription": user_text, "response": bot_text}))
                if audio_bytes:
                    await websocket.send_bytes(audio_bytes)
            except Exception:
                break
        elif "text" in msg:
            try:
                data = json.loads(msg["text"])
            except Exception:
                data = None
            if isinstance(data, dict) and data.get("type") == "ping":
                try:
                    await websocket.send_text(json.dumps({"type": "pong"}))
                except Exception:
                    break
            else:
                continue
        else:
            break

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
