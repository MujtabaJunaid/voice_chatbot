import uvicorn
from fastapi import FastAPI, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from groq import Groq
import whisper
from gtts import gTTS
import os
import webrtcvad
import wave

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

model = whisper.load_model("base")
client = Groq()
chat_memory = []
vad = webrtcvad.Vad(2)

def apply_vad(audio_bytes, sample_rate=16000, frame_duration=30):
    frame_size = int(sample_rate * frame_duration / 1000 * 2)
    frames = [audio_bytes[i:i + frame_size] for i in range(0, len(audio_bytes), frame_size)]
    voiced = b''.join([f for f in frames if len(f) == frame_size and vad.is_speech(f, sample_rate)])
    return voiced if voiced else audio_bytes

@app.post("/transcribe/")
async def transcribe_audio(file: UploadFile):
    with open("temp.wav", "wb") as f:
        f.write(await file.read())
    result = model.transcribe("temp.wav")
    user_text = result["text"]
    chat_memory.append({"role": "user", "content": user_text})
    if len(chat_memory) > 3:
        chat_memory.pop(0)
    messages = [{"role": m["role"], "content": m["content"]} for m in chat_memory]
    completion = client.chat.completions.create(model="llama3-8b-8192", messages=messages)
    bot_response = completion.choices[0].message.content
    chat_memory.append({"role": "assistant", "content": bot_response})
    if len(chat_memory) > 3:
        chat_memory.pop(0)
    tts = gTTS(bot_response)
    tts.save("response.mp3")
    return {"transcription": user_text, "response": bot_response, "audio_file": "response.mp3"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_bytes()
        with open("raw_input.wav", "wb") as f:
            f.write(data)
        wf = wave.open("raw_input.wav", "rb")
        audio_bytes = wf.readframes(wf.getnframes())
        wf.close()
        voiced_audio = apply_vad(audio_bytes)
        with open("temp.wav", "wb") as f:
            f.write(voiced_audio)
        result = model.transcribe("temp.wav")
        user_text = result["text"]
        chat_memory.append({"role": "user", "content": user_text})
        if len(chat_memory) > 3:
            chat_memory.pop(0)
        messages = [{"role": m["role"], "content": m["content"]} for m in chat_memory]
        completion = client.chat.completions.create(model="llama3-8b-8192", messages=messages)
        bot_response = completion.choices[0].message.content
        chat_memory.append({"role": "assistant", "content": bot_response})
        if len(chat_memory) > 3:
            chat_memory.pop(0)
        tts = gTTS(bot_response)
        tts.save("response.mp3")
        with open("response.mp3", "rb") as f:
            audio_reply = f.read()
        await websocket.send_json({"transcription": user_text, "response": bot_response})
        await websocket.send_bytes(audio_reply)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
