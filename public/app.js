document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const tabRecord = document.getElementById('tabRecord');
    const tabUpload = document.getElementById('tabUpload');
    const panelRecord = document.getElementById('panelRecord');
    const panelUpload = document.getElementById('panelUpload');

    const recordBtn = document.getElementById('recordBtn');
    const recordBtnInner = document.getElementById('recordBtnInner');
    const micIcon = document.getElementById('micIcon');
    const timerEl = document.getElementById('timer');
    const visualizerCanvas = document.getElementById('visualizer');

    const dropZone = document.getElementById('dropZone');
    const audioFileInput = document.getElementById('audioFileInput');
    const fileInfo = document.getElementById('fileInfo');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const removeFileBtn = document.getElementById('removeFileBtn');

    const taskSelect = document.getElementById('taskSelect');
    const transcribeBtn = document.getElementById('transcribeBtn');

    const loadingState = document.getElementById('loadingState');
    const loadingText = document.getElementById('loadingText');
    const errorBanner = document.getElementById('errorBanner');
    const errorMessage = document.getElementById('errorMessage');
    const closeError = document.getElementById('closeError');

    const resultSection = document.getElementById('resultSection');
    const resultText = document.getElementById('resultText');
    const metaInfo = document.getElementById('metaInfo');
    const copyBtn = document.getElementById('copyBtn');
    const downloadBtn = document.getElementById('downloadBtn');
    const clearBtn = document.getElementById('clearBtn');

    // State Variables
    let activeTab = 'record'; // 'record' or 'upload'
    let mediaRecorder = null;
    let audioChunks = [];
    let recordedBlob = null;
    let uploadedFile = null;
    let isRecording = false;
    let timerInterval = null;
    let secondsElapsed = 0;

    // Audio Context & Visualizer variables
    let audioCtx = null;
    let analyser = null;
    let microphoneStream = null;
    let animationId = null;

    // --- Tab Switching ---
    tabRecord.addEventListener('click', () => {
        if (isRecording) return;
        activeTab = 'record';
        tabRecord.className = "flex-1 py-2.5 text-sm font-medium rounded-lg bg-indigo-600 text-white shadow-md transition-all duration-200 flex items-center justify-center gap-2";
        tabUpload.className = "flex-1 py-2.5 text-sm font-medium rounded-lg text-slate-400 hover:text-slate-200 transition-all duration-200 flex items-center justify-center gap-2";
        panelRecord.classList.remove('hidden');
        panelUpload.classList.add('hidden');
        updateTranscribeButtonState();
    });

    tabUpload.addEventListener('click', () => {
        if (isRecording) return;
        activeTab = 'upload';
        tabUpload.className = "flex-1 py-2.5 text-sm font-medium rounded-lg bg-indigo-600 text-white shadow-md transition-all duration-200 flex items-center justify-center gap-2";
        tabRecord.className = "flex-1 py-2.5 text-sm font-medium rounded-lg text-slate-400 hover:text-slate-200 transition-all duration-200 flex items-center justify-center gap-2";
        panelUpload.classList.remove('hidden');
        panelRecord.classList.add('hidden');
        updateTranscribeButtonState();
    });

    // --- Audio Recording Logic ---
    recordBtn.addEventListener('click', async () => {
        if (!isRecording) {
            await startRecording();
        } else {
            stopRecording();
        }
    });

    async function startRecording() {
        audioChunks = [];
        recordedBlob = null;
        hideError();

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            microphoneStream = stream;

            mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });

            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) audioChunks.push(e.data);
            };

            mediaRecorder.onstop = () => {
                recordedBlob = new Blob(audioChunks, { type: 'audio/webm' });
                updateTranscribeButtonState();
            };

            mediaRecorder.start();
            isRecording = true;

            // Update UI for recording state
            recordBtnInner.className = "relative w-20 h-20 bg-red-600 border-2 border-red-400 rounded-full flex items-center justify-center text-white transition-all duration-200 shadow-xl shadow-red-600/30 animate-pulse";
            micIcon.innerHTML = '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>';

            // Start Timer
            secondsElapsed = 0;
            timerEl.textContent = "00:00";
            timerInterval = setInterval(() => {
                secondsElapsed++;
                const mins = String(Math.floor(secondsElapsed / 60)).padStart(2, '0');
                const secs = String(secondsElapsed % 60).padStart(2, '0');
                timerEl.textContent = `${mins}:${secs}`;
            }, 1000);

            // Setup Visualizer
            setupVisualizer(stream);

        } catch (err) {
            console.error('Microphone error:', err);
            showError('Microphone permission denied or not available. Please check your browser permissions.');
        }
    }

    function stopRecording() {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
        }

        if (microphoneStream) {
            microphoneStream.getTracks().forEach(track => track.stop());
        }

        isRecording = false;
        clearInterval(timerInterval);
        cancelAnimationFrame(animationId);

        // Reset Record Button UI
        recordBtnInner.className = "relative w-20 h-20 bg-slate-900 border-2 border-slate-700 rounded-full flex items-center justify-center text-slate-100 transition-all duration-200 shadow-xl group-active:scale-95";
        micIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 100-6 3 3 0 000 6z"></path>';

        clearCanvas();
    }

    // --- Audio Visualizer Setup ---
    function setupVisualizer(stream) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioCtx.createAnalyser();
        const source = audioCtx.createMediaStreamSource(stream);

        source.connect(analyser);
        analyser.fftSize = 64;

        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        const canvas = visualizerCanvas;
        const canvasCtx = canvas.getContext('2d');

        // Set canvas resolution match display
        canvas.width = canvas.offsetWidth;
        canvas.height = canvas.offsetHeight;

        function draw() {
            animationId = requestAnimationFrame(draw);

            analyser.getByteFrequencyData(dataArray);

            canvasCtx.fillStyle = 'rgb(15, 23, 42)'; // bg-slate-950
            canvasCtx.fillRect(0, 0, canvas.width, canvas.height);

            const barWidth = (canvas.width / bufferLength) * 2.5;
            let barHeight;
            let x = 0;

            for (let i = 0; i < bufferLength; i++) {
                barHeight = (dataArray[i] / 255) * canvas.height;

                // Gradient for bars
                const gradient = canvasCtx.createLinearGradient(0, canvas.height, 0, 0);
                gradient.addColorStop(0, '#6366f1'); // Indigo
                gradient.addColorStop(1, '#a855f7'); // Purple

                canvasCtx.fillStyle = gradient;
                canvasCtx.fillRect(x, canvas.height - barHeight, barWidth, barHeight);

                x += barWidth + 2;
            }
        }

        draw();
    }

    function clearCanvas() {
        const canvas = visualizerCanvas;
        if (!canvas) return;
        const canvasCtx = canvas.getContext('2d');
        canvasCtx.fillStyle = 'rgb(15, 23, 42)';
        canvasCtx.fillRect(0, 0, canvas.width, canvas.height);
    }

    // --- File Upload Logic ---
    dropZone.addEventListener('click', () => audioFileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('border-indigo-500', 'bg-indigo-500/5');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('border-indigo-500', 'bg-indigo-500/5');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('border-indigo-500', 'bg-indigo-500/5');
        if (e.dataTransfer.files.length > 0) {
            handleSelectedFile(e.dataTransfer.files[0]);
        }
    });

    audioFileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleSelectedFile(e.target.files[0]);
        }
    });

    function handleSelectedFile(file) {
        // Validate file size (25MB limit)
        if (file.size > 25 * 1024 * 1024) {
            showError('File size exceeds the 25MB limit.');
            return;
        }

        uploadedFile = file;
        fileName.textContent = file.name;
        fileSize.textContent = `${(file.size / (1024 * 1024)).toFixed(2)} MB`;

        dropZone.classList.add('hidden');
        fileInfo.classList.remove('hidden');
        hideError();
        updateTranscribeButtonState();
    }

    removeFileBtn.addEventListener('click', () => {
        uploadedFile = null;
        audioFileInput.value = '';
        fileInfo.classList.add('hidden');
        dropZone.classList.remove('hidden');
        updateTranscribeButtonState();
    });

    // --- Button State Handler ---
    function updateTranscribeButtonState() {
        if (activeTab === 'record') {
            transcribeBtn.disabled = !recordedBlob;
        } else {
            transcribeBtn.disabled = !uploadedFile;
        }
    }

    // --- Transcribe API Request ---
    transcribeBtn.addEventListener('click', async () => {
        hideError();
        resultSection.classList.add('hidden');

        let audioFileToSend = null;
        if (activeTab === 'record') {
            if (!recordedBlob) return;
            audioFileToSend = new File([recordedBlob], "recording.webm", { type: 'audio/webm' });
        } else {
            if (!uploadedFile) return;
            audioFileToSend = uploadedFile;
        }

        const task = taskSelect.value;

        const formData = new FormData();
        formData.append('audio', audioFileToSend);
        formData.append('task', task);

        // Show loading state
        loadingState.classList.remove('hidden');
        loadingText.textContent = task === 'translate' ? 'Translating audio to English with Whisper...' : 'Transcribing audio with Whisper...';
        transcribeBtn.disabled = true;

        try {
            const response = await fetch('/api/transcribe', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Transcription failed.');
            }

            // Display results
            resultText.value = data.text;
            metaInfo.textContent = `Detected Language: ${data.language.toUpperCase()} (${(data.language_probability * 100).toFixed(1)}%)`;
            resultSection.classList.remove('hidden');
            resultSection.scrollIntoView({ behavior: 'smooth' });

        } catch (err) {
            console.error('Transcription error:', err);
            showError(err.message || 'An unexpected error occurred during transcription.');
        } finally {
            loadingState.classList.add('hidden');
            updateTranscribeButtonState();
        }
    });

    // --- Result Action Buttons ---
    copyBtn.addEventListener('click', () => {
        resultText.select();
        navigator.clipboard.writeText(resultText.value);
        const originalText = copyBtn.innerHTML;
        copyBtn.innerHTML = '<svg class="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Copied!';
        setTimeout(() => {
            copyBtn.innerHTML = originalText;
        }, 2000);
    });

    downloadBtn.addEventListener('click', () => {
        const text = resultText.value;
        const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `transcript_${new Date().toISOString().slice(0, 10)}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    });

    clearBtn.addEventListener('click', () => {
        resultSection.classList.add('hidden');
        resultText.value = '';
        recordedBlob = null;
        uploadedFile = null;
        audioFileInput.value = '';
        fileInfo.classList.add('hidden');
        dropZone.classList.remove('hidden');
        updateTranscribeButtonState();
    });

    // --- Error Helpers ---
    function showError(msg) {
        errorMessage.textContent = msg;
        errorBanner.classList.remove('hidden');
    }

    function hideError() {
        errorBanner.classList.add('hidden');
    }

    closeError.addEventListener('click', hideError);
});
