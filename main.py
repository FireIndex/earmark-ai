from dotenv import load_dotenv
load_dotenv()

from utils.audio_processor import process_input
from utils import cache
from core.transcriber import transcribe_all
from core.analyzer import MeetingAnalysis, analyze, to_display
from core.rag_engine import build_rag_chain, ask_question

def run_pipeline(source: str, language: str = "english", on_step=None) -> dict:
    """
    on_step(step, detail) reports progress to a UI. step is one of
    "fetch", "listen", "read", "remember"; detail is a short string or None.
    """
    def step(name, detail=None):
        if on_step:
            on_step(name, detail)

    print("starting AI Video Assistant")

    key = cache.source_key(source, language)
    cached = cache.load(key)

    # 1. Transcript (Whisper), cached on disk per video/file
    if "transcript" in cached:
        print("Using cached transcript.")
        step("fetch", "cached")
        step("listen", "cached")
        transcript = cached["transcript"]
    else:
        step("fetch")
        chunks = process_input(source)

        def on_progress(done, total):
            if done < 0:
                step("listen", "queued")
            else:
                step("listen", f"{done}/{total}")

        step("listen", f"0/{len(chunks)}")
        transcript = transcribe_all(chunks, language, on_progress=on_progress)
        cached["transcript"] = transcript
        cache.save(key, cached)
    print(f"raw transcription (first 300 characters ) {transcript[:300]}")

    # 2. Title, summary, action items, decisions, questions: ONE LLM call, cached
    if "analysis" in cached:
        print("Using cached analysis (0 LLM calls).")
        step("read", "cached")
        analysis = MeetingAnalysis.model_validate(cached["analysis"])
    else:
        step("read")
        analysis = analyze(transcript)
        cached["analysis"] = analysis.model_dump()
        cache.save(key, cached)

    # 3. RAG: separate vector collection per meeting
    step("remember")
    rag_chain = build_rag_chain(transcript, collection_name=f"meeting_{key}")

    return {
        **to_display(analysis),
        "key": key,
        "analysis": analysis,
        "transcript": transcript,
        "rag_chain": rag_chain,
    }

if __name__ == "__main__":
    # CLI entry point
    source = input("Enter YouTube URL or local file path: ").strip()
    language = input("Language (english/hinglish): ").strip() or "english"
    result = run_pipeline(source, language)

    print("\n" + "=" * 60)
    print(f"📌 Title: {result['title']}")
    print(f"\n📋 Summary:\n{result['summary']}")
    print(f"\n✅ Action Items:\n{result['action_items']}")
    print(f"\n🔑 Key Decisions:\n{result['key_decisions']}")
    print(f"\n❓ Open Questions:\n{result['open_questions']}")
    print("=" * 60)

    # Phase 2 — Chat with your meeting via RAG
    print("\n💬 Chat with your meeting (type 'exit' to quit)\n")
    rag_chain = result["rag_chain"]
    while True:
        question = input("You: ").strip()
        if question.lower() in ["exit", "quit", "q"]:
            print("👋 Goodbye!")
            break
        if not question:
            continue
        answer = ask_question(rag_chain, question)
        print(f"\n🤖 Assistant: {answer}\n")