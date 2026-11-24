import glob
import re
import yt_dlp
from pydub import AudioSegment
import os

DOWNLOAD_DIR = '.temp/downloade'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
DEFAULT_COOKIES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cookies.txt")

def _youtube_id(url: str):
    match = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})", url)
    return match.group(1) if match else None


def download_youtube_audio(url: str) -> str:
    # Skip the download if this video was already saved in DOWNLOAD_DIR
    video_id = _youtube_id(url)
    if video_id:
        # glob.escape: the [ ] around the ID are literal, not a character class
        pattern = os.path.join(DOWNLOAD_DIR, glob.escape(f"[{video_id}]") + " *.og.wav")
        existing = sorted(glob.glob(pattern))
        if existing:
            print(f"Already downloaded, reusing: {existing[0]}")
            return existing[0]

    output_path = os.path.join(DOWNLOAD_DIR, "[%(id)s] %(title)s.og.%(ext)s")
    ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_path,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                    "preferredquality": "192",
                }
            ],
            "quiet": True,
            # YouTube's JS "n challenge" needs a JS runtime (deno) + yt-dlp's solver script.
            # Without it only thumbnails are listed -> "Requested format is not available".
            "js_runtimes": {"deno": {}},
            "remote_components": {"ejs:github"},
        }

    # YouTube may demand sign-in ("confirm you're not a bot"). Supply cookies via:
    #   YTDLP_COOKIES_FILE=path/to/cookies.txt   (Netscape format, most reliable)
    #   YTDLP_COOKIES_BROWSER=firefox            (or edge/chrome/brave; browser should be closed)
    #   ...or just drop a cookies.txt in the project root.
    cookies_file = os.getenv("YTDLP_COOKIES_FILE") or (
        DEFAULT_COOKIES_FILE if os.path.isfile(DEFAULT_COOKIES_FILE) else None
    )
    cookies_browser = os.getenv("YTDLP_COOKIES_BROWSER")
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file
    elif cookies_browser:
        ydl_opts["cookiesfrombrowser"] = (cookies_browser,)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # Post-processor converts to .wav regardless of the original extension
        filename = os.path.splitext(ydl.prepare_filename(info))[0] + ".wav"
    return filename


def convert_to_wav(input_path: str) -> str:
    """Convert any audio/video file to WAV format using pydub"""
    output_path = os.path.splitext(input_path)[0] + "_converted.wav"
    audio = AudioSegment.from_file(input_path)
    audio = audio.set_channels(1).set_frame_rate(16000) #16khz
    audio.export(output_path, format="wav")
    return output_path


def chunk_audio(wav_path: str, chunk_minutes: int = 5) -> list:
    audio = AudioSegment.from_wav(wav_path)
    chunk_ms = chunk_minutes * 60 * 1000 
    chunks = []

    for i, start in enumerate(range(0, len(audio), chunk_ms)):
        chunk = audio[start : start + chunk_ms]
        chunk_path = f"{wav_path}_chunk_{i}.wav"
        chunk.export(chunk_path , format="wav")
        chunks.append(chunk_path)
    return chunks


def process_input(source: str) -> list:
    if source.startswith("http://") or source.startswith("https://"):
        print("Detected YouTube URL. Downloading audio...")
        wav_path = download_youtube_audio(source)
    else:
        print("Detected local file. Converting to WAV...")
        wav_path = convert_to_wav(source)

    print("Chunking audio...")
    chunks = chunk_audio(wav_path)
    print(f"Audio ready — {len(chunks)} chunk(s) created.")
    return chunks


if __name__ == "__main__":
    print(chunk_audio(convert_to_wav(download_youtube_audio("https://www.youtube.com/watch?v=cQmf2MvkPQ0"))))
