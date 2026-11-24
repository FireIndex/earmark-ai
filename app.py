"""
Earmark: Streamlit UI for the meeting assistant.

Run:  streamlit run app.py

Multi-user notes:
- Everything a person sees (their meetings, their chats) lives in st.session_state,
  so each browser session gets its own private "desk".
- Heavy things are shared by all users in the process: one Whisper model (jobs take
  turns, see core/transcriber.py), one embedding model, one LLM client, and the disk
  cache, so a video one person already processed is instant for the next.

Styling notes:
- st.html runs content through a sanitizer: inline <svg> is stripped (icons are
  <img> data URLs, see ui/art.py) and a <style> containing "<" is dropped entirely.
"""
import datetime as dt
import html
import os
import re
import time
import uuid

import streamlit as st

st.set_page_config(
    page_title="Earmark · meeting notes",
    page_icon=":material/graphic_eq:",
    layout="wide",
    initial_sidebar_state="auto",
)

from main import run_pipeline  # noqa: E402  (also loads .env)
from ui import art  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(ROOT, ".temp", "uploads")
AUDIO_TYPES = ["mp3", "wav", "m4a", "mp4", "mkv", "mov", "webm", "ogg", "flac", "aac"]
SUGGESTIONS = ["What are the next steps?", "Who owns what?", "Give me the 3-line version"]

# (pipeline step, name on the tile, what it means when idle)
STAGES = [
    ("fetch", "Grab", "link or file"),
    ("listen", "Listen", "speech → text"),
    ("read", "Note", "summary + to-dos"),
    ("remember", "Chat", "ask anything"),
]
HEADLINES = {
    "fetch": "Grabbing the audio",
    "listen": "Listening",
    "read": "Writing your notes",
    "remember": "Getting the chat ready",
}
TIPS = {
    None: "warming up…",
    "fetch": "downloading + converting the audio",
    "listen": "long meetings are cut into 5-minute parts, transcribed one by one",
    "read": "one pass over the transcript: summary, to-dos, decisions, questions",
    "remember": "indexing the transcript so you can ask questions",
}

e = html.escape
ss = st.session_state
ss.setdefault("meetings", {})    # key -> meeting dict; private to this browser session
ss.setdefault("current", None)   # key of the open meeting
ss.setdefault("job", None)       # pending/running pipeline job
ss.setdefault("error", None)     # (title, hint, detail) from the last failed job
ss.setdefault("pending_q", None) # question picked from a suggestion chip


# ───────────────────────── helpers ─────────────────────────
def inject_css():
    with open(os.path.join(ROOT, "ui", "style.css"), encoding="utf-8") as f:
        css = f.read()
    if "<" in css:
        raise ValueError("ui/style.css must not contain '<' — Streamlit's sanitizer would drop it")
    st.html(f"<style>{css}</style>")


def topbar():
    st.html(f'<div class="topbar"><div class="brand">{art.img(art.LOGO)}<b>Earmark</b></div>'
            f'<span class="flow">MEETING → NOTES → CHAT</span></div>')


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def unknown(value: str) -> bool:
    return not value or value.strip().lower() in {"not specified", "unknown", "n/a", "none", "-"}


def source_label(src: str) -> str:
    if src.startswith(("http://", "https://")):
        return "YouTube" if re.search(r"youtu\.?be", src) else src[:60]
    return src


def friendly_error(exc: Exception) -> tuple[str, str, str]:
    msg = str(exc).lower()
    detail = f"{type(exc).__name__}: {exc}"[:1200]
    if "sign in" in msg or "not a bot" in msg or "cookies" in msg:
        return ("YouTube wants a sign-in for this one.",
                "Refresh cookies.txt in the project folder, or upload the recording instead.", detail)
    if "rate limit" in msg or "429" in msg or "too many requests" in msg:
        return ("Whoa, too fast.", "The AI is rate-limited right now. Give it a minute, then try again.", detail)
    if "api key" in msg or "401" in msg or "authentication" in msg or "unauthorized" in msg:
        return ("The API key didn't work.", "Check the key for your LLM provider in .env.", detail)
    if "unsupported url" in msg or "is not a valid url" in msg or "video unavailable" in msg:
        return ("That link didn't lead to a video.", "Double-check it, or upload the recording instead.", detail)
    if "ffmpeg" in msg or "decod" in msg or "could not find codec" in msg or "invalid data" in msg:
        return ("Couldn't open that recording.", "Try an mp3, wav, m4a or mp4 file.", detail)
    return ("Something broke along the way.", "Try again. If it keeps happening, the details below will help.", detail)


def save_upload(upload) -> str:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(upload.name)[1].lower() or ".bin"
    path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{ext}")
    with open(path, "wb") as f:
        f.write(upload.getbuffer())
    return path


def start_job(source: str, language: str, label: str):
    ss.job = {"source": source, "language": language, "label": label}
    ss.error = None


def open_meeting(key):
    ss.current = key


def new_meeting():
    ss.current = None
    ss.error = None


def pick_suggestion(widget_key: str):
    ss.pending_q = ss[widget_key]
    ss[widget_key] = None


def notes_markdown(m: dict) -> str:
    a = m["analysis"]
    out = [f"# {a.title}", "", f"_Noted {m['noted']:%d %b %Y, %H:%M} from {m['source']}_", "", "## Summary"]
    out += [f"- {b}" for b in a.summary] or ["- (none)"]
    out += ["", "## Action items"]
    out += [f"- [ ] {x.task} (owner: {x.owner}, deadline: {x.deadline})" for x in a.action_items] or ["- (none)"]
    out += ["", "## Key decisions"]
    out += [f"- {d}" for d in a.key_decisions] or ["- (none)"]
    out += ["", "## Open questions"]
    out += [f"- {q}" for q in a.open_questions] or ["- (none)"]
    out += ["", "## Transcript", "", m["transcript"]]
    return "\n".join(out)


# ───────────────────────── stage track (explainer + live progress) ─────────────────────────
def track_html(states: dict | None = None, subs: dict | None = None, listen_frac: float | None = None) -> str:
    """states=None renders the idle explainer; otherwise name -> todo|now|done."""
    parts = []
    for i, (name, label, idle_sub) in enumerate(STAGES):
        state = (states or {}).get(name, "idle")
        icon = art.img(art.STAGE_ICONS[name](anim=state == "now"), "ico", label)
        extra = ""
        if state == "done":
            extra = art.img(art.CHECK, "badge", "done")
        elif state == "now":
            extra = '<span class="tag">NOW</span>'
        sub = (subs or {}).get(name) or {"idle": idle_sub, "todo": "up next", "now": "working…", "done": "done"}[state]
        mini = ""
        if state == "now" and name == "listen" and listen_frac is not None:
            mini = f'<div class="mini"><i style="width:{round(listen_frac * 100)}%"></i></div>'
        parts.append(f'<div class="stage {state}"><span class="num">0{i + 1}</span>{extra}{icon}'
                     f'<b>{label}</b><small>{e(sub)}</small>{mini}</div>')
        if i < len(STAGES) - 1:
            parts.append(f'<div class="link{" lit" if state == "done" else ""}"></div>')
    return f'<div class="track{" idle" if states is None else ""}">{"".join(parts)}</div>'


# ───────────────────────── sidebar: this user's desk ─────────────────────────
def sidebar():
    if not ss.meetings:
        return  # empty sidebar stays hidden on a first visit
    busy = ss.job is not None
    with st.sidebar:
        st.html('<div class="side-title">Your desk</div><div class="side-sub">MEETINGS FROM THIS VISIT</div>')
        st.button("New meeting", icon=":material/add:", type="primary", width="stretch",
                  disabled=busy, on_click=new_meeting)
        for key, m in reversed(list(ss.meetings.items())):
            wkey = f"open_cur_{key}" if key == ss.current else f"open_{key}"
            st.button(m["title"], key=wkey, width="stretch", disabled=busy,
                      on_click=open_meeting, args=(key,))
        st.html('<div class="side-foot">🔒 only you can see this desk</div>')


# ───────────────────────── view: home ─────────────────────────
def view_home():
    topbar()
    words = ["TRANSCRIBE", "SUMMARIZE", "TO-DOS", "DECISIONS", "OPEN QUESTIONS", "ASK ANYTHING", "YOUTUBE", "MP3 · MP4 · WAV"]
    belt = "".join(f"<span>{w}<i>✦</i></span>" for w in words)
    st.html(f'<div class="ticker"><div class="belt">{belt}{belt}</div></div>')
    st.html(f'<div class="hero"><h1>Meetings <span class="hl y">in.</span><br>'
            f'Notes <span class="hl p">out.</span>{art.img(art.STAR, "star")}</h1>'
            '<p>Then chat with it like you were in the room.</p></div>')
    st.html(track_html())

    with st.container(key="intake"):
        st.html('<div class="intake-head"><b>Drop a meeting</b><span>~1 MIN PER 10 MIN OF AUDIO</span></div>')
        if ss.error:
            title, hint, detail = ss.error
            st.html(f'<div class="err">{art.img(art.OOPS)}<div><b>{e(title)}</b><span>{e(hint)}</span></div></div>')
            with st.expander("What went wrong, exactly"):
                st.code(detail, language=None, wrap_lines=True)

        c1, c2 = st.columns(2, vertical_alignment="center")
        with c1:
            mode = st.segmented_control("Source", [":material/link: Link", ":material/upload: File"],
                                        default=":material/link: Link", key="mode") or ":material/link: Link"
        with c2:
            lang = st.segmented_control("Spoken in", ["English", "Hinglish"], default="English",
                                        key="lang") or "English"

        is_link = mode.endswith("Link")
        if is_link:
            url = st.text_input("YouTube link", key="url", placeholder="https://youtube.com/watch?v=…",
                                label_visibility="collapsed")
            upload = None
        else:
            upload = st.file_uploader("Recording", type=AUDIO_TYPES, key="upload",
                                      label_visibility="collapsed")
            url = ""

        oops = st.empty()
        if st.button("Make my notes  →", type="primary", width="stretch"):
            if is_link:
                u = url.strip()
                if not u:
                    oops.html('<div class="oops-line">↑ paste a link first</div>')
                elif not re.match(r"https?://", u):
                    oops.html('<div class="oops-line">↑ that should start with https://</div>')
                else:
                    start_job(u, lang.lower(), u)
                    st.rerun()
            elif upload is None:
                oops.html('<div class="oops-line">↑ pick a recording first</div>')
            else:
                start_job(save_upload(upload), lang.lower(), upload.name)
                st.rerun()

    st.html('<div class="foot"><b>PRIVATE</b> your meetings + chats stay in your own session</div>')


# ───────────────────────── view: working ─────────────────────────
def _sub(step: str, detail):
    if detail == "cached":
        return "already done ⚡"
    if step == "listen" and detail and "/" in detail:
        done, total = (int(x) for x in detail.split("/"))
        return "done" if done >= total else f"part {done + 1} of {total}"
    return None


def _percent(state) -> int:
    if state["finished"]:
        return 100
    step = state["step"]
    if step == "fetch":
        return 4
    if step == "listen":
        done, total = state.get("chunks", (0, 1))
        return 10 + int(64 * done / max(total, 1))
    return {"read": 78, "remember": 93}.get(step, 1)


def working_html(job, state) -> str:
    names = [n for n, *_ in STAGES]
    idx = len(names) if state["finished"] else (names.index(state["step"]) if state["step"] else -1)
    states = {n: ("done" if i < idx else "now" if i == idx else "todo") for i, n in enumerate(names)}

    step = state["step"]
    if state["finished"]:
        headline = "Done! Opening your notes"
    elif state["queued"]:
        headline = "In line for the listener"
    else:
        headline = HEADLINES.get(step, "Starting up")
        sub = state["subs"].get(step)
        if sub and sub != "done":
            headline += f" · {sub}"

    listen_frac = None
    if "chunks" in state:
        d, t = state["chunks"]
        listen_frac = d / max(t, 1)

    queued = ('<div class="queued">👋 Someone else\'s meeting is being transcribed. Yours starts right after.</div>'
              if state["queued"] else "")
    pct = _percent(state)
    return f"""
<div class="work-head">
  <div class="pct">{pct}<span>%</span></div>
  <div>
    <div class="now-line"><span class="dot"></span>{e(headline)}</div>
    <span class="src">{e(source_label(job['label']))}</span>
  </div>
</div>
{track_html(states, state["subs"], listen_frac)}
<div class="bigbar"><i style="width:{pct}%"></i></div>
<div class="tip">{e("all set" if state["finished"] else TIPS.get(step, ""))}</div>
{queued}"""


def view_working():
    topbar()
    job = ss.job
    state = {"step": None, "subs": {}, "queued": False, "finished": False}
    board = st.empty()

    def paint():
        board.html(working_html(job, state))

    def on_step(name, detail):
        state["step"] = name
        if name == "listen" and detail == "queued":
            state["queued"] = True
        else:
            if name == "listen" and detail and "/" in detail:
                state["queued"] = False
                state["chunks"] = tuple(int(x) for x in detail.split("/"))
            state["subs"][name] = _sub(name, detail)
        paint()

    paint()
    try:
        result = run_pipeline(job["source"], job["language"], on_step=on_step)
    except Exception as exc:  # st.rerun/stop are BaseException, so they pass through
        ss.error = friendly_error(exc)
        ss.job = None
        st.rerun()

    state["finished"] = True
    paint()
    time.sleep(0.9)  # let the user see 100% before the notes open

    key = result["key"]
    if key in ss.meetings:  # same recording again: keep its chat, move it to the top
        m = ss.meetings.pop(key)
    else:
        m = {"chat": [], "noted": dt.datetime.now(), "source": source_label(job["label"])}
    a = result["analysis"]
    m.update(title=a.title, analysis=a, transcript=result["transcript"], chain=result["rag_chain"])
    ss.meetings[key] = m
    ss.current = key
    ss.job = None
    st.rerun()


# ───────────────────────── view: meeting ─────────────────────────
def notes_column(m: dict):
    a = m["analysis"]

    bullets = "".join(f"<li>{e(b)}</li>" for b in a.summary) or '<div class="empty">nothing to summarize</div>'
    st.html(f'<div class="card yellow"><span class="label">THE GIST</span><ul>{bullets}</ul></div>')

    if a.action_items:
        rows = []
        for x in a.action_items:
            who = ('<span class="chip c-unk">no owner yet</span>' if unknown(x.owner)
                   else f'<span class="chip c-who">@ {e(x.owner)}</span>')
            when = ('<span class="chip c-unk">no date</span>' if unknown(x.deadline)
                    else f'<span class="chip c-when">⏰ {e(x.deadline)}</span>')
            rows.append(f'<div class="task"><span class="box"></span><div><b>{e(x.task)}</b>'
                        f'<div class="chips">{who}{when}</div></div></div>')
        body = "".join(rows)
    else:
        body = '<div class="empty">no to-dos came up</div>'
    st.html(f'<div class="card white"><span class="label">TO-DO · {len(a.action_items)}</span>{body}</div>')

    body = ("".join(f'<div class="row"><span class="ic">✓</span><span>{e(d)}</span></div>' for d in a.key_decisions)
            or '<div class="empty">nothing was settled</div>')
    st.html(f'<div class="card mint"><span class="label">DECIDED</span>{body}</div>')

    body = ("".join(f'<div class="row"><span class="ic">?</span><span>{e(q)}</span></div>' for q in a.open_questions)
            or '<div class="empty">no loose ends</div>')
    st.html(f'<div class="card lilac"><span class="label">STILL OPEN</span>{body}</div>')

    st.write("")
    with st.expander("Full transcript", icon=":material/subject:"):
        st.html(f'<div class="transcript">{e(m["transcript"])}</div>')


def bubble(role: str, text: str, idx: int):
    with st.container(key=f"bubble_{role}_{idx}"):
        st.html(f'<span class="who">{"you" if role == "user" else "earmark"}</span>')
        st.markdown(text)


def chat_column(key: str, m: dict):
    a = m["analysis"]
    with st.container(key="chatcard"):
        st.html(f'<div class="chat-head">{art.img(art.chat())}<div><b>Ask the meeting</b>'
                '<span>ANSWERS COME ONLY FROM WHAT WAS SAID</span></div></div>')
        log = st.container(height=470, border=False, key="chatlog")
        with log:
            intro = st.empty()
            if not m["chat"]:
                with intro.container():
                    st.html(f'<div class="chat-empty">{art.img(art.chat(anim=True))}<b>What do you want to know?</b>'
                            '<span>TAP ONE OR TYPE YOUR OWN</span></div>')
                    options = list(SUGGESTIONS)
                    if a.open_questions:
                        q0 = a.open_questions[0]
                        options.append(q0 if len(q0) <= 70 else q0[:67] + "…")
                    wkey = f"suggest_{key}"
                    st.pills("Suggestions", options, key=wkey, label_visibility="collapsed",
                             on_change=pick_suggestion, args=(wkey,))
            for i, msg in enumerate(m["chat"]):
                bubble(msg["role"], msg["content"], i)

        typed = st.chat_input("Ask about decisions, owners, dates…", key=f"ask_{key}")
        question = typed or ss.pending_q
        ss.pending_q = None
        if not question:
            return

        intro.empty()
        n = len(m["chat"])
        with log:
            bubble("user", question, n)
            with st.container(key=f"bubble_assistant_{n + 1}"):
                st.html('<span class="who">earmark</span>')
                thinking = st.empty()
                thinking.html('<span class="thinking">searching the transcript<i>…</i></span>')

                def stream():
                    first = True
                    for chunk in m["chain"].stream(question):
                        if first:
                            thinking.empty()
                            first = False
                        yield chunk

                try:
                    answer = st.write_stream(stream())
                except Exception as exc:
                    thinking.empty()
                    title, hint, _ = friendly_error(exc)
                    answer = f"**{title}** {hint}"
                    st.markdown(answer)
                if not isinstance(answer, str) or not answer.strip():
                    answer = "I couldn't find an answer to that. Try rephrasing?"
                    thinking.empty()
                    st.markdown(answer)

        m["chat"].append({"role": "user", "content": question})
        m["chat"].append({"role": "assistant", "content": answer})


def view_meeting(key: str):
    m = ss.meetings[key]
    a = m["analysis"]
    topbar()

    minutes = max(1, round(len(m["transcript"].split()) / 150))
    noted = m["noted"]
    head, actions = st.columns([4, 1.2], vertical_alignment="bottom")
    with head:
        st.html(f'<div class="m-head"><div class="m-meta"><b>{e(m["source"]).upper()}</b>'
                f'noted {noted.day} {noted:%b}, {noted:%H:%M}</div><h1>{e(a.title)}</h1></div>')
    with actions:
        slug = re.sub(r"[^a-z0-9]+", "-", a.title.lower()).strip("-") or "meeting"
        st.download_button("Download notes", notes_markdown(m), file_name=f"{slug}.md",
                           mime="text/markdown", icon=":material/download:", width="stretch")
        st.button("New meeting", icon=":material/add:", width="stretch", on_click=new_meeting,
                  key="new_from_head")

    st.html('<div class="stats">'
            f'<div class="stat"><b>{len(a.action_items)}</b><span>to-dos</span></div>'
            f'<div class="stat"><b>{len(a.key_decisions)}</b><span>decisions</span></div>'
            f'<div class="stat"><b>{len(a.open_questions)}</b><span>open questions</span></div>'
            f'<div class="stat"><b>{minutes}</b><span>min of talk</span></div></div>')

    left, right = st.columns([1.25, 1], gap="large")
    with left:
        notes_column(m)
    with right:
        chat_column(key, m)


# ───────────────────────── router ─────────────────────────
inject_css()
sidebar()
if ss.job:
    view_working()
elif ss.current in ss.meetings:
    view_meeting(ss.current)
else:
    view_home()
