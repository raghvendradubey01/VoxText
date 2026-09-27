from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from faster_whisper import WhisperModel
import shutil
import os
import uuid

app = FastAPI()

# Load the model (default to 'small' for a balance of speed/accuracy)
# The model will download on the first run.
model = WhisperModel("small", device="cpu", compute_type="int8")

# Ensure a directory exists for temporary audio uploads
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    task: str = Form("transcribe")
):
    # Save the uploaded file temporarily
    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{audio.filename}")

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)

    try:
        # Run Whisper transcription
        segments, info = model.transcribe(file_path, beam_size=5, task=task)

        full_text = " ".join([segment.text for segment in segments])

        return {
            "text": full_text,
            "language": info.language,
            "language_probability": info.language_probability
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up file
        if os.path.exists(file_path):
            os.remove(file_path)

# Serve the frontend
app.mount("/", StaticFiles(directory="public", html=True), name="public")
