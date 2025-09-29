import os
from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import FileResponse
from groq import Groq
from gtts import gTTS
from dotenv import load_dotenv
import uvicorn
import tempfile

load_dotenv()

app = FastAPI()
client = Groq(api_key=os.getenv("groq_api_key"))
chat_history = []

@app.post("/chat/")
async def chat(audio: UploadFile, user_id: str = Form("default_user")):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(await audio.read())
        tmp_path = tmp.name
    with open(tmp_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            file=audio_file,
            model="whisper-large-v3"
        )
    user_message = transcription.text
    chat_history.append({"role": "user", "content": user_message})
    if len(chat_history) > 6:
        chat_history[:] = chat_history[-6:]
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=chat_history
    )
    bot_message = response.choices[0].message.content
    chat_history.append({"role": "assistant", "content": bot_message})
    tts = gTTS(bot_message)
    tts_path = tempfile.mktemp(suffix=".mp3")
    tts.save(tts_path)
    return FileResponse(tts_path, media_type="audio/mpeg")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

