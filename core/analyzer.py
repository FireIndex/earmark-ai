import json
import os

from pydantic import BaseModel, Field
from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.llm import get_llm

# Transcripts up to this many characters go to the LLM in ONE call.
# ~20k chars is about 5k tokens, which fits Groq free-tier tokens-per-minute limits.
# On a paid tier, raise it (e.g. LLM_MAX_CHARS=200000 in .env) so long meetings are 1 call too.
MAX_CHARS_PER_CALL = int(os.getenv("LLM_MAX_CHARS", "20000"))


class ActionItem(BaseModel):
    task: str = Field(description="Task description")
    owner: str = Field(description="Who is responsible, or 'Not specified'")
    deadline: str = Field(description="Deadline if mentioned, else 'Not specified'")


class MeetingAnalysis(BaseModel):
    title: str = Field(description="Short professional meeting title, max 8 words")
    summary: list[str] = Field(description="Professional meeting summary as bullet points")
    action_items: list[ActionItem] = Field(description="All action items")
    key_decisions: list[str] = Field(description="Key decisions made")
    open_questions: list[str] = Field(description="Unresolved questions or topics needing follow-up")


ANALYZE_PROMPT = (
    "You are an expert meeting analyst. From the meeting transcript, produce: "
    "a short professional title (max 8 words); a concise summary as bullet points; "
    "all action items (task, owner, deadline; use 'Not specified' when unknown); "
    "key decisions made; and unresolved questions or topics needing follow-up. "
    "Use empty lists when nothing is found. Do not invent facts."
)

MERGE_PROMPT = (
    "You are an expert meeting analyst. You are given JSON analyses of consecutive parts "
    "of ONE meeting. Merge them into a single analysis of the whole meeting: one title, "
    "one deduplicated bullet-point summary, and deduplicated action items, key decisions "
    "and open questions. Drop open questions that a later part resolves."
)


def _run(system_prompt: str, text: str) -> MeetingAnalysis:
    llm = get_llm().with_structured_output(MeetingAnalysis)
    result = llm.invoke([("system", system_prompt), ("human", text)])
    if result is None:
        raise ValueError("LLM did not return a structured analysis")
    return result


def analyze(transcript: str) -> MeetingAnalysis:
    """1 LLM call for normal transcripts; N parts + 1 merge call for very long ones."""
    if len(transcript) <= MAX_CHARS_PER_CALL:
        print("Analyzing transcript (1 LLM call)...")
        return _run(ANALYZE_PROMPT, transcript)

    splitter = RecursiveCharacterTextSplitter(chunk_size=MAX_CHARS_PER_CALL, chunk_overlap=500)
    parts = splitter.split_text(transcript)
    partials = []
    for i, part in enumerate(parts, 1):
        print(f"Analyzing part {i}/{len(parts)}...")
        prompt = f"{ANALYZE_PROMPT} This is part {i} of {len(parts)} of a longer transcript; analyze only this part."
        partials.append(_run(prompt, part))

    print("Merging partial analyses...")
    merged_input = json.dumps([p.model_dump() for p in partials], ensure_ascii=False)
    return _run(MERGE_PROMPT, merged_input)


def _numbered(items: list[str], empty: str) -> str:
    return "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1)) or empty


def to_display(analysis: MeetingAnalysis) -> dict:
    """Plain-text fields, same keys run_pipeline returned before."""
    return {
        "title": analysis.title,
        "summary": "\n".join(f"• {b}" for b in analysis.summary),
        "action_items": _numbered(
            [f"{a.task} (Owner: {a.owner}, Deadline: {a.deadline})" for a in analysis.action_items],
            "No action items found.",
        ),
        "key_decisions": _numbered(analysis.key_decisions, "No key decisions found."),
        "open_questions": _numbered(analysis.open_questions, "No open questions found."),
    }
