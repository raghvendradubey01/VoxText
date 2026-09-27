# Whisper AI Transcriber

A modern, local, privacy-first speech-to-text web application powered by **Faster-Whisper** and **FastAPI**, featuring a sleek Tailwind CSS frontend with a real-time canvas audio visualizer.

---

## Project Structure

```
whisper-app/
├── public/                 # Static Frontend
│   ├── index.html          # Responsive Web Interface
│   ├── style.css           # Custom CSS styling
│   └── app.js              # Recording, visualizer, drag-and-drop & API integration
├── main.py                 # FastAPI backend & Faster-Whisper local engine
├── requirements.txt        # Python package dependencies
└── README.md               # Setup and execution instructions
```

---

## Installation & Setup Instructions

### Prerequisites
- Python 3.9 or higher installed on your system.
- A microphone (optional, for voice recording).

### Step 1: Install Dependencies
Open your terminal inside the `whisper-app` directory and install the required Python packages:

```bash
pip install -r requirements.txt
```

*(Note: The first time you run the application, `faster-whisper` will automatically download the default Whisper model weights to your system cache).*

---

## Running the Application

Start the FastAPI backend server using Uvicorn:

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Once running, open your web browser and navigate to:
🚧 Live Demo: Coming Soon

---

## Features
1. **Voice Recording**: Real-time voice recording with dynamic canvas waveform visualization and running timer.
2. **Audio Upload**: Drag-and-drop or file selection for existing audio files (`.mp3`, `.wav`, `.m4a`, `.webm`, `.ogg`).
3. **Translation & Transcription**: Support for transcribing speech or translating foreign audio directly into English.
4. **Result Management**: One-click text copying, direct `.txt` file downloading, and clear options.
5. **Privacy First**: Everything runs entirely on your local machine with zero external API keys or cloud dependencies.
