"""Animated scene for the GSTR-2B download dashboard, built from the supplied 3D-cartoon art.

build_scene(periods, states, working) -> one-line SVG string (no newlines / blank lines,
which Streamlit's markdown parser would otherwise break). SCENE_CSS holds the animations.
Art lives in modules/gstr2b_assets.py (embedded WebP, generated from the asset sheet).
"""
import html
import re

from modules.gstr2b_assets import B64, SIZE

_AB = {"January": "JAN", "February": "FEB", "March": "MAR", "April": "APR", "May": "MAY", "June": "JUN",
       "July": "JUL", "August": "AUG", "September": "SEP", "October": "OCT", "November": "NOV", "December": "DEC"}

SCENE_CSS = re.sub(r"\s*\n\s*", "", """
.g2b-scene{display:block!important;padding:0!important;min-height:0!important}
.g2b-scene svg{display:block;width:100%;height:auto}
.q-eye{animation:q-eye 4s infinite}
.q-key{animation:q-key .5s steps(1) infinite}
.q-lamp{animation:q-lamp .9s ease-in-out infinite alternate;transform-box:fill-box;transform-origin:center}
.q-claw{animation:q-claw 1.3s ease-in-out infinite}
.q-belt{animation:q-belt .8s linear infinite}
.q-spin{animation:q-spin 1s linear infinite;transform-box:fill-box;transform-origin:center}
.q-cur{animation:q-glow 1.6s ease-in-out infinite}
.q-pop{animation:q-pop .4s ease-out;transform-box:fill-box;transform-origin:center}
.q-steam{animation:q-steam 2.4s ease-in-out infinite}
.q-spark{animation:q-spark 1.1s ease-in-out infinite}
.q-folder{animation:q-bob 2s ease-in-out infinite}
.q-sway{animation:q-sway 4s ease-in-out infinite alternate;transform-box:fill-box;transform-origin:50% 100%}
.q-c1{animation:q-drift 11s ease-in-out infinite alternate}
.q-c2{animation:q-drift 15s ease-in-out infinite alternate-reverse}
.g2b-idle svg *{animation-play-state:paused!important}
@keyframes q-eye{0%,93%,100%{opacity:0}95%,97%{opacity:1}}
@keyframes q-key{0%{opacity:0}50%{opacity:1}}
@keyframes q-lamp{from{opacity:.25;transform:scale(.9)}to{opacity:1;transform:scale(1.12)}}
@keyframes q-claw{0%,100%{transform:translateY(0)}50%{transform:translateY(6px)}}
@keyframes q-belt{to{transform:translateX(28px)}}
@keyframes q-spin{to{transform:rotate(360deg)}}
@keyframes q-glow{50%{opacity:.55}}
@keyframes q-pop{0%{transform:scale(.3)}80%{transform:scale(1.25)}100%{transform:scale(1)}}
@keyframes q-steam{0%{opacity:0;transform:translateY(4px)}50%{opacity:.8}100%{opacity:0;transform:translateY(-8px)}}
@keyframes q-spark{50%{opacity:.2}}
@keyframes q-bob{50%{transform:translateY(-4px)}}
@keyframes q-sway{to{transform:rotate(2.5deg)}}
@keyframes q-drift{to{transform:translateX(26px)}}
""")


def _img(name, x, y, cls="", extra=""):
    w, h = SIZE[name]
    c = f' class="{cls}"' if cls else ""
    return f'<image{c} href="data:image/webp;base64,{B64[name]}" x="{x:.1f}" y="{y:.1f}" width="{w}" height="{h}"{extra}/>'


# ---- fixed layout (viewBox 1000 x 300) -------------------------------------------------
_CLAW_X, _ELBOW_Y = 700, 62
_TILE_W, _TILE_H, _PITCH, _TILE_BOTTOM = 56, 70, 62, 228
_WIN = (548, 905)                         # visible belt window for period tiles


def _icon(st, cx, cy):
    if st in ("downloaded", "complete"):
        return (f'<g class="q-pop"><circle cx="{cx}" cy="{cy}" r="9" fill="#17b26a"/>'
                f'<path d="M{cx - 4} {cy} l3 3.4 l5.4-6.4" stroke="#fff" stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></g>')
    if st in ("downloading", "converting"):
        return (f'<g class="q-spin"><circle cx="{cx}" cy="{cy}" r="8" fill="none" stroke="#d6e6fb" stroke-width="3"/>'
                f'<path d="M{cx} {cy - 8} a8 8 0 0 1 8 8" stroke="#2779f5" stroke-width="3" fill="none" stroke-linecap="round"/></g>')
    if st == "failed":
        return (f'<circle cx="{cx}" cy="{cy}" r="9" fill="#e5483a"/><text x="{cx}" y="{cy + 5}" font-size="13" font-weight="900" '
                f'fill="#fff" text-anchor="middle">!</text>')
    return (f'<circle cx="{cx}" cy="{cy}" r="8" fill="none" stroke="#b9c7da" stroke-width="2"/>'
            f'<path d="M{cx} {cy - 5} v5 l3 2" stroke="#b9c7da" stroke-width="2" fill="none" stroke-linecap="round"/>')


def _tile(x, month, year, st):
    ab = _AB.get(month, month[:3].upper())
    cx = x + _TILE_W / 2
    y = _TILE_BOTTOM - _TILE_H
    cur = st in ("downloading", "converting")
    ring = (f'<rect class="q-cur" x="{x - 1}" y="{y - 1}" width="{_TILE_W + 2}" height="{_TILE_H + 2}" rx="6" '
            f'fill="none" stroke="#2779f5" stroke-width="2.5"/>') if cur else ""
    return (f'<g><image href="data:image/webp;base64,{B64["doc"]}" x="{x:.1f}" y="{y}" width="{_TILE_W}" height="{_TILE_H}" preserveAspectRatio="none"/>{ring}'
            f'<text x="{cx:.1f}" y="{y + 29}" font-size="11" font-weight="800" fill="#1b2f5b" text-anchor="middle">{ab}</text>'
            f'<text x="{cx:.1f}" y="{y + 40}" font-size="9" fill="#5a6f8c" text-anchor="middle">{html.escape(str(year))}</text>'
            f'{_icon(st, round(cx), y + 55)}</g>')


def build_scene(periods, states, working=True):
    periods = list(periods)
    st_of = lambda m, y: (states.get(f"{m} {y}") or {}).get("state", "pending")
    sts = [st_of(m, y) for m, y in periods]
    n = len(periods)
    done_n = sum(1 for s in sts if s in ("downloaded", "complete", "converting"))
    all_done = n > 0 and all(s in ("complete", "downloaded") for s in sts)
    # tile under the claw: the one being worked on, else first still waiting, else the last
    act = next((i for i, s in enumerate(sts) if s in ("downloading", "converting")), None)
    if act is None:
        act = next((i for i, s in enumerate(sts) if s == "pending"), max(0, n - 1))
    tiles = "".join(_tile(_CLAW_X - _TILE_W / 2 + (i - act) * _PITCH, m, y, sts[i]) for i, (m, y) in enumerate(periods))

    mx, my = 10, 13                        # mascot origin
    parts = [
        '<defs>'
        f'<clipPath id="qwin"><rect x="{_WIN[0]}" y="120" width="{_WIN[1] - _WIN[0]}" height="130"/></clipPath>'
        '<clipPath id="qbelt"><rect x="528" y="219" width="372" height="10" rx="5"/></clipPath>'
        '<linearGradient id="qpil" x1="0" x2="1"><stop offset="0" stop-color="#2d4d80"/><stop offset=".5" stop-color="#1f3a63"/><stop offset="1" stop-color="#16294a"/></linearGradient>'
        '</defs>',
        '<ellipse cx="500" cy="262" rx="470" ry="26" fill="#e6f1fc"/>',
        f'<g class="q-c1">{_img("cloud1", 300, 6)}</g><g class="q-c2">{_img("cloud2", 760, 18)}</g>',
        f'<g class="q-sway">{_img("plant", -4, 176)}</g>',
        '<rect x="0" y="246" width="266" height="18" rx="7" fill="#ecd3a8"/><rect x="0" y="258" width="266" height="6" rx="3" fill="#d9bb8a"/>',
        _img("mascot_open", mx, my),
        _img("mascot_closed", mx + 4, my, "q-eye"),
        _img("laptop", 150, 176),
        _img("arms_a", mx + 41, my + 159),
        _img("arms_b", mx + 41.4, my + 159, "q-key"),
        _img("mug", 4, 222),
        '<g class="q-steam"><path d="M22 218 q-4-6 0-12 q4-6 0-12" stroke="#a9bdd6" stroke-width="2.2" fill="none" stroke-linecap="round"/></g>',
        _img("stack", 200, 216),
        # forearm hangs from the elbow, claw down (drawn first so the elbow cap covers its end)
        f'<g class="q-claw"><g transform="translate({_CLAW_X} {_ELBOW_Y}) rotate(90) translate(-4 -17)">{_img("forearm", 0, 0)}</g></g>',
        _img("robot_arm", _CLAW_X - 187, _ELBOW_Y - 64),
        _img("machine", 262, 30),
        _img("lamp", 369, 20, "q-lamp"),
        _img("conveyor", 520, 214),
        '<g clip-path="url(#qbelt)"><g class="q-belt" fill="#6f95c4" opacity=".55">' + "".join(f'<rect x="{510 + k * 28}" y="221" width="12" height="3" rx="1.5"/>' for k in range(16)) + '</g></g>',
        f'<g clip-path="url(#qwin)">{tiles}</g>',
        '<rect x="550" y="118" width="26" height="112" rx="6" fill="url(#qpil)"/><rect x="540" y="218" width="46" height="12" rx="5" fill="#16294a"/>',
    ]
    if all_done:
        parts.append(''.join(f'<line class="q-spark" x1="{a}" y1="{b}" x2="{c}" y2="{d}" stroke="#ffc533" stroke-width="3" stroke-linecap="round"/>'
                             for a, b, c, d in ((918, 150, 910, 136), (945, 142, 945, 126), (972, 150, 982, 136), (992, 168, 1000, 160))))
    parts.append(f'<g class="q-folder">{_img("folder", 906, 166)}</g>'
                 f'<text x="951" y="282" font-size="12" font-weight="800" fill="#7a5a00" text-anchor="middle">{done_n} / {n} ready</text>')
    return ('<svg viewBox="0 0 1000 292" role="img" aria-label="GSTR-2B download animation">' + "".join(parts) + '</svg>').replace("\n", "")
