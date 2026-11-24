"""
Chunky, flat icons. Streamlit's HTML sanitizer strips inline <svg>, so every icon is
shipped as <img src="data:image/svg+xml;base64,...">. SMIL animations inside still run.
"""
import base64

INK = "#141414"
YELLOW = "#FFD23F"
PINK = "#FF5FA2"
BLUE = "#3D5AFE"
MINT = "#3DDC97"
LILAC = "#B69CFF"
WHITE = "#FFFFFF"


def img(svg: str, cls: str = "", alt: str = "") -> str:
    data = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f'<img class="{cls}" alt="{alt}" src="data:image/svg+xml;base64,{data}"/>'


def _svg(body: str, box: str = "0 0 64 64") -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{box}">{body}</svg>'


def _spin(cx, cy, dur="1.1s"):
    return (f'<animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" '
            f'to="360 {cx} {cy}" dur="{dur}" repeatCount="indefinite"/>')


def cassette(anim: bool = False) -> str:
    reel = lambda x: (f'<g><circle cx="{x}" cy="28" r="5.5" fill="{WHITE}" stroke="{INK}" stroke-width="2.5"/>'
                      f'<path d="M{x} 23.5v9M{x - 4.5} 28h9" stroke="{INK}" stroke-width="2.2" stroke-linecap="round"/>'
                      f'{_spin(x, 28) if anim else ""}</g>')
    return _svg(
        f'<rect x="5" y="13" width="54" height="38" rx="7" fill="{YELLOW}" stroke="{INK}" stroke-width="3"/>'
        f'<rect x="12" y="19" width="40" height="18" rx="4" fill="{WHITE}" stroke="{INK}" stroke-width="2.5"/>'
        f'{reel(23)}{reel(41)}'
        f'<path d="M17 51l4-7.5h22l4 7.5" fill="{PINK}" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>'
    )


def headphones(anim: bool = False) -> str:
    bars = ""
    for i, x in enumerate((25, 30.5, 36)):
        h0, h1 = (8, 18) if i != 1 else (12, 22)
        a = (f'<animate attributeName="height" values="{h0};{h1};{h0}" dur=".7s" begin="{i * .18}s" repeatCount="indefinite"/>'
             f'<animate attributeName="y" values="{52 - h0};{52 - h1};{52 - h0}" dur=".7s" begin="{i * .18}s" repeatCount="indefinite"/>'
             if anim else "")
        bars += f'<rect x="{x}" y="{52 - h0}" width="4" height="{h0}" rx="2" fill="{BLUE}">{a}</rect>'
    return _svg(
        f'<path d="M12 40v-8a20 20 0 0 1 40 0v8" fill="none" stroke="{INK}" stroke-width="3.5" stroke-linecap="round"/>'
        f'<rect x="6" y="35" width="13" height="19" rx="5" fill="{PINK}" stroke="{INK}" stroke-width="3"/>'
        f'<rect x="45" y="35" width="13" height="19" rx="5" fill="{PINK}" stroke="{INK}" stroke-width="3"/>'
        f'{bars}'
    )


def notepad(anim: bool = False) -> str:
    wiggle = ('<animateTransform attributeName="transform" type="translate" values="0 0;-4 3;2 -1;0 0" '
              'dur=".65s" repeatCount="indefinite"/>' if anim else "")
    return _svg(
        f'<rect x="12" y="9" width="34" height="46" rx="5" fill="{WHITE}" stroke="{INK}" stroke-width="3"/>'
        f'<path d="M12 18v-4a5 5 0 0 1 5-5h24a5 5 0 0 1 5 5v4z" fill="{MINT}" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>'
        f'<path d="M19 27h20M19 34h20M19 41h11" stroke="{INK}" stroke-width="2.6" stroke-linecap="round"/>'
        f'<g>{wiggle}<path d="M38 52l15-15 5.5 5.5-15 15-7.5 2z" fill="{YELLOW}" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>'
        f'<path d="M49 41l5.5 5.5" stroke="{INK}" stroke-width="3"/></g>'
    )


def chat(anim: bool = False) -> str:
    dots = ""
    for i, x in enumerate((35, 42, 49)):
        a = (f'<animate attributeName="opacity" values="1;.15;1" dur="1s" begin="{i * .2}s" repeatCount="indefinite"/>'
             if anim else "")
        dots += f'<circle cx="{x}" cy="42" r="2.6" fill="{INK}">{a}</circle>'
    return _svg(
        f'<path d="M9 10h28a5 5 0 0 1 5 5v13a5 5 0 0 1-5 5H22l-8 7v-7H9a5 5 0 0 1-5-5V15a5 5 0 0 1 5-5z" '
        f'fill="{BLUE}" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>'
        f'<path d="M29 30h26a5 5 0 0 1 5 5v13a5 5 0 0 1-5 5h-4v7l-8-7H29a5 5 0 0 1-5-5V35a5 5 0 0 1 5-5z" '
        f'fill="{PINK}" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>{dots}'
    )


STAGE_ICONS = {"fetch": cassette, "listen": headphones, "read": notepad, "remember": chat}

LOGO = _svg(
    f'<rect x="3" y="3" width="34" height="34" rx="10" fill="{YELLOW}" stroke="{INK}" stroke-width="3"/>'
    + "".join(f'<rect x="{x}" y="{20 - h / 2}" width="3.4" height="{h}" rx="1.7" fill="{INK}"/>'
              for x, h in ((9.5, 7), (14.5, 15), (19.5, 22), (24.5, 13), (29.5, 6))),
    "0 0 40 40",
)

CHECK = _svg(
    f'<circle cx="20" cy="20" r="16.5" fill="{MINT}" stroke="{INK}" stroke-width="3"/>'
    f'<path d="M12.5 20.5l5 5 10-11" fill="none" stroke="{INK}" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "0 0 40 40",
)

OOPS = _svg(
    f'<circle cx="24" cy="24" r="20" fill="{PINK}" stroke="{INK}" stroke-width="3"/>'
    f'<path d="M24 12.5v15" stroke="{INK}" stroke-width="4.2" stroke-linecap="round"/>'
    f'<circle cx="24" cy="34.5" r="2.8" fill="{INK}"/>',
    "0 0 48 48",
)

STAR = _svg(
    f'<path d="M20 2l4.5 13.5L38 20l-13.5 4.5L20 38l-4.5-13.5L2 20l13.5-4.5z" fill="{YELLOW}" stroke="{INK}" '
    f'stroke-width="2.6" stroke-linejoin="round"/>',
    "0 0 40 40",
)
