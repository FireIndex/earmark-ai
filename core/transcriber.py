import whisper
import os
import threading

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")

_model = None
_whisper_lock = threading.Lock()

def load_mode():
    global _model
    if _model is None:
        print(f"Loading Whisper model: {WHISPER_MODEL} ...")
        _model = whisper.load_model(WHISPER_MODEL) 
        print("Whisper model loaded.")
    return _model

def transcribe_chunk_whisper(chunk_path: str) -> str:
    model = load_mode()
    print(f"Using whisper for transcription.")
    result = model.transcribe(chunk_path, task="transcribe")  
    return result["text"]

def transcribe_chunk(chunk_path: str, language: str = "english") -> str:
    """
    Route one chunk to Whisper or Sarvam depending on language choice.
    - english  → Whisper (local model)
    - hinglish → Sarvam (translates to English while transcribing)
    """
    if language.lower() == "hinglish":
        pass
        # return transcribe_chunk_sarvam(chunk_path)
    return transcribe_chunk_whisper(chunk_path)

def transcribe_all(chunks: list, language: str = "english", on_progress=None) -> str:
    """
    on_progress(done, total) is called after each chunk; on_progress(-1, total) means
    another user's job is using Whisper and this one is waiting its turn.
    One Whisper model is shared by every user, so jobs take turns via _whisper_lock.
    """
    if not _whisper_lock.acquire(blocking=False):
        if on_progress:
            on_progress(-1, len(chunks))
        _whisper_lock.acquire()

    try:
        texts = []
        for i, chunk in enumerate(chunks):
            print(f"Transcribing chunk {i + 1}/{len(chunks)}...")
            if on_progress:
                on_progress(i, len(chunks))
            texts.append(transcribe_chunk(chunk, language=language))
        if on_progress:
            on_progress(len(chunks), len(chunks))
    finally:
        _whisper_lock.release()

    print("Transcription complete.")
    return " ".join(texts).strip()

if __name__ == "__main__":
    print(transcribe_chunk_whisper(r"D:\CODE\Audio-Assistance\downloades\[cQmf2MvkPQ0] The Brutal Reality of AI Engineering in Late 2026_converted.wav_chunk_2.wav"))