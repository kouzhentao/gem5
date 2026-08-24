#!/usr/bin/env python3
"""Generate SVG diagrams for docs/ax46mpv.md."""
from __future__ import annotations

import html
from pathlib import Path

OUT = Path(__file__).parent / "ax46mpv"

STYLES = """
  text { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px; fill: #1e293b; }
  .sans { font-family: system-ui, -apple-system, sans-serif; }
  .title { font-size: 14px; font-weight: 600; fill: #0f172a; }
  .hdr { fill: #475569; font-weight: 600; font-size: 11px; }
  .row { fill: #64748b; font-weight: 600; font-size: 11px; }
  .box { fill: #ffffff; stroke: #94a3b8; stroke-width: 1.2; }
  .panel { fill: #f8fafc; stroke: #cbd5e1; stroke-width: 1.5; }
  .blue { fill: #eff6ff; stroke: #3b82f6; }
  .orange { fill: #fff7ed; stroke: #f97316; }
  .green { fill: #ecfdf5; stroke: #10b981; }
  .cell { fill: #f8fafc; stroke: #e2e8f0; stroke-width: 1; }
  .cell-hi { fill: #dbeafe; stroke: #93c5fd; stroke-width: 1; }
  .cell-stall { fill: #fef3c7; stroke: #fbbf24; stroke-width: 1; }
  .arrow { stroke: #475569; stroke-width: 1.5; fill: none; marker-end: url(#arrow); }
"""

ARROW = """
<marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
  <path d="M0,0 L8,4 L0,8 Z" fill="#475569"/>
</marker>
"""


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def wrap_svg(body: str, w: int, h: int) -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">\n'
        f"<defs>{ARROW}<style>{STYLES}</style></defs>\n"
        f"{body}\n</svg>\n"
    )


def box(x, y, w, h, text, cls="box", fs=12, anchor="middle"):
    rx = 6
    lines = text.split("\n")
    ty = y + h / 2 - (len(lines) - 1) * 7 + 4
    parts = [
        f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>'
    ]
    for i, line in enumerate(lines):
        parts.append(
            f'<text x="{x + w/2}" y="{ty + i * 14}" text-anchor="{anchor}" '
            f'font-size="{fs}">{esc(line)}</text>'
        )
    return "\n".join(parts)


def arrow_v(x, y1, y2):
    return f'<line class="arrow" x1="{x}" y1="{y1}" x2="{x}" y2="{y2}"/>'


def arrow_h(x1, x2, y):
    return f'<line class="arrow" x1="{x1}" y1="{y}" x2="{x2}" y2="{y}"/>'


def timing_svg(cols: list[str], rows: list[str], cells: dict[tuple[str, str], str],
               highlights: set[tuple[str, str]] | None = None,
               stalls: set[tuple[str, str]] | None = None,
               title: str = "") -> str:
    highlights = highlights or set()
    stalls = stalls or set()
    cw, rh, pad = 72, 28, 48
    lw = pad + 36
    w = lw + len(cols) * cw + 20
    h = 30 + len(rows) * rh + 20
    parts: list[str] = []
    if title:
        parts.append(f'<text class="title sans" x="16" y="22">{esc(title)}</text>')
    y0 = 36
    for j, c in enumerate(cols):
        parts.append(
            f'<text class="hdr" x="{lw + j * cw + cw/2}" y="{y0 - 8}" '
            f'text-anchor="middle">{esc(c)}</text>'
        )
    for i, row in enumerate(rows):
        y = y0 + i * rh
        parts.append(f'<text class="row" x="{pad}" y="{y + rh/2 + 4}">{esc(row)}</text>')
        for j, c in enumerate(cols):
            x = lw + j * cw
            key = (row, c)
            txt = cells.get(key, "")
            cls = "cell"
            if key in stalls:
                cls = "cell-stall"
            elif key in highlights or txt:
                cls = "cell-hi" if txt else "cell"
            parts.append(
                f'<rect class="{cls}" x="{x+2}" y="{y+2}" width="{cw-4}" height="{rh-4}" rx="4"/>'
            )
            if txt:
                for k, line in enumerate(txt.split("\n")):
                    parts.append(
                        f'<text x="{x + cw/2}" y="{y + rh/2 + 4 + k * 13}" '
                        f'text-anchor="middle" font-size="10">{esc(line)}</text>'
                    )
    return wrap_svg("\n".join(parts), w, h)


def gen_data_ctrl():
    w, h = 860, 520
    b = []
    b.append('<rect class="panel" x="20" y="20" width="400" height="480" rx="10"/>')
    b.append('<text class="title sans" x="40" y="48">数据通路</text>')
    chain = [
        ("PC / NPC", 70), ("instr 32b", 122), ("ctrl 375b", 174),
        ("ii_src1..4 64b", 226), ("ex_src*_reg", 278), ("mm_src*_reg", 330),
        ("lx_src*_reg", 382),
    ]
    for i, (t, y) in enumerate(chain):
        b.append(box(130, y, 180, 32, t, "blue"))
        if i < len(chain) - 1:
            b.append(arrow_v(220, y + 32, chain[i + 1][1]))
    b.append(box(285, 318, 140, 32, "alu0/1 @EX", "blue"))
    b.append('<line class="arrow" x1="220" y1="294" x2="355" y2="294"/>')
    b.append('<line class="arrow" x1="355" y1="294" x2="355" y2="318"/>')
    b.append(box(285, 442, 140, 32, "alu2/3 @LX", "blue"))
    b.append('<line class="arrow" x1="220" y1="398" x2="355" y2="398"/>')
    b.append('<line class="arrow" x1="355" y1="398" x2="355" y2="442"/>')

    b.append('<rect class="panel" x="440" y="20" width="400" height="480" rx="10"/>')
    b.append('<text class="title sans" x="460" y="48">控制通路</text>')
    ctrl = [
        (470, 80, 200, "kv_iiu_scb hazard"), (490, 138, 160, "ii_*_stall"),
        (520, 196, 100, "IIQ"),
    ]
    for x, y, wbox, t in ctrl:
        b.append(box(x, y, wbox, 32, t, "orange"))
    b.append(arrow_v(570, 112, 138))
    b.append(arrow_v(570, 170, 196))
    ctrl2 = [(470, 260, 200, "mm_i0_mispred"), (490, 318, 160, "mm_redirect"),
             (465, 376, 210, "iiq_flush / kill")]
    for x, y, wbox, t in ctrl2:
        b.append(box(x, y, wbox, 32, t, "orange"))
    b.append(arrow_v(570, 292, 318))
    b.append(arrow_v(570, 350, 376))
    b.append(box(490, 440, 160, 32, "lx_stall", "orange"))
    b.append(box(710, 440, 110, 32, "停 II..LX", "orange"))
    b.append(arrow_h(650, 710, 456))
    (OUT / "data-ctrl.svg").write_text(wrap_svg("\n".join(b), w, h), encoding="utf-8")


def gen_fetch():
    """Horizontal fetch pipeline: PC mux → f0 → f1/ITLB → f2/ICU → FQ."""
    w, h = 1180, 300
    b = []
    b.append('<text class="title sans" x="590" y="22" text-anchor="middle">取指通路（左 → 右，方框 = 寄存器）</text>')

    def mux(x, y, wbox, hbox, title, inputs):
        b.append(box(x, y, wbox, hbox, title, "orange", 10))
        b.append(f'<polygon points="{x+wbox//2-14},{y+hbox+2} {x+wbox//2+14},{y+hbox+2} {x+wbox//2},{y+hbox+16}" fill="#f97316"/>')
        b.append(f'<text x="{x+wbox//2}" y="{y+hbox+28}" text-anchor="middle" font-size="9">{esc(inputs)}</text>')

    # redirect / backend feedback (top)
    b.append(box(30, 42, 100, 36, "redirect_pc\n(mm/wb/resume)", "orange", 9))
    b.append(box(150, 42, 120, 36, "kv_bpu\nBTB/BHT/RAS", "blue", 9))
    b.append(arrow_h(250, 310, 78))
    b.append('<text x="268" y="74" font-size="9">bpu_info_target</text>')

    # target_pc mux
    mux(310, 48, 130, 44, "target_pc\nMUX", "BTB target | bblk+8 | seq_pc")
    b.append(arrow_h(130, 150, 60))
    b.append('<text x="158" y="38" font-size="8">redirect</text>')

    # seq_pc +8
    b.append(box(470, 42, 90, 36, "seq_pc\n(+8/ issue)", "panel", 9))
    b.append(arrow_h(440, 470, 60))

    # req_addr mux
    mux(580, 48, 120, 44, "req_addr\nMUX", "redirect | f0_pc | target_pc")
    b.append(arrow_h(250, 580, 60))

    # f0 register
    b.append(box(730, 40, 90, 52, "f0_pc\nf0_valid", "green", 10))
    b.append(arrow_h(700, 730, 66))
    b.append('<text x="714" y="38" font-size="8">hold</text>')

    # fetch_issue → f1
    b.append(arrow_h(820, 860, 66))
    b.append('<text x="828" y="58" font-size="9">fetch_issue</text>')
    b.append(box(860, 40, 90, 52, "f1_va\nf1_valid", "green", 10))

    # ITLB
    b.append(box(860, 108, 90, 40, "ITLB\n→ f1_pa", "blue", 9))
    b.append(arrow_v(905, 92, 108))

    # f2
    b.append(arrow_h(950, 990, 66))
    b.append(box(990, 40, 90, 52, "f2_va\nf2_pa\nf2_valid", "green", 10))

    # ICU / ILM
    b.append(box(990, 108, 90, 52, "ICU(I$)\n或 ILM", "blue", 10))
    b.append(arrow_v(1035, 92, 108))
    b.append('<text x="1000" y="168" font-size="8">VIPT: idx[10:6]</text>')
    b.append('<text x="1000" y="180" font-size="8">tag=PA高位</text>')

    # kv_pq align + FQ
    b.append(arrow_h(1080, 1120, 66))
    b.append(box(1120, 48, 50, 36, "FQ", "panel", 10))

    # pred bundle bottom
    b.append(box(310, 200, 200, 44, "kv_pq：对齐 RVC\nifu_i0/i1_pc, pred_npc", "panel", 9))
    b.append(arrow_h(1035, 410, 222))
    b.append('<text x="720" y="222" font-size="9">fetch_resp → fq_wr</text>')

    (OUT / "fetch.svg").write_text(wrap_svg("\n".join(b), w, h), encoding="utf-8")


def gen_block():
    """Top-level left-to-right pipeline (registers as boxes)."""
    w, h = 1100, 200
    b = []
    b.append('<text class="title sans" x="550" y="22" text-anchor="middle">标量后端概览（左 → 右）</text>')
    stages = [
        (40, "取指\nf0→f1→f2→FQ", "blue", 100),
        (160, "译码\nid_*", "box", 80),
        (260, "IIQ", "green", 50),
        (330, "发射\nii_*", "box", 80),
        (430, "EX\nex_*", "blue", 70),
        (520, "MM\nmm_*", "box", 70),
        (610, "LX\nlx_*", "blue", 70),
        (700, "WB\nwb_*", "green", 70),
    ]
    for i, (x, label, cls, ww) in enumerate(stages):
        b.append(box(x, 50, ww, 56, label, cls, 10))
        if i < len(stages) - 1:
            nx = stages[i + 1][0]
            b.append(arrow_h(x + ww, nx - 4, 78))
    # side units
    b.append(box(820, 40, 80, 40, "kv_lsu", "orange", 9))
    b.append(box(820, 90, 80, 40, "kv_mdu", "orange", 9))
    b.append(arrow_h(500, 820, 60))
    b.append('<text x="530" y="56" font-size="8">ls/mdu req</text>')
    b.append(box(920, 40, 100, 40, "kv_bpu\n← mm update", "orange", 9))
    b.append(arrow_h(770, 920, 130))
    b.append('<text x="800" y="138" font-size="8">mm_redirect → 取指</text>')
    (OUT / "block.svg").write_text(wrap_svg("\n".join(b), w, h), encoding="utf-8")


def gen_fq():
    w, h = 620, 200
    b = []
    b.append('<text class="title sans" x="16" y="22">FQ — Fetch Queue（kv_fq.v）</text>')
    b.append('<text x="40" y="58" font-size="11">IC (f2 fetch_resp)</text>')
    b.append('<text x="480" y="58" font-size="11">ID (kv_dec)</text>')
    b.append(arrow_h(160, 200, 70))
    b.append('<text x="175" y="62" font-size="10">fq_wr</text>')
    b.append(arrow_h(420, 480, 70))
    b.append('<text x="430" y="62" font-size="10">fq_rd</text>')
    b.append(box(120, 80, 380, 90,
                 "s0[0..3] 环形 RAM，每项 75b\n"
                 "wptr / rptr\n"
                 "每拍 fq_wr 入队 1 bundle（最多 4×16b）\n"
                 "每拍 fq_rd 出队 0~2 条 → fq_i0 / fq_i1", "panel", 11, "middle"))
    (OUT / "fq.svg").write_text(wrap_svg("\n".join(b), w, h), encoding="utf-8")


def gen_iiq():
    w, h = 680, 210
    b = []
    b.append('<text class="title sans" x="16" y="22">IIQ — Issue Instruction Queue（kv_iiq.v）</text>')
    b.append('<text x="30" y="58" font-size="11">ID</text>')
    b.append('<text x="560" y="58" font-size="11">IS (kv_iiu)</text>')
    b.append(arrow_h(60, 180, 70))
    b.append('<text x="70" y="62" font-size="9">iiq_w_valid</text>')
    b.append(arrow_h(500, 560, 70))
    b.append('<text x="510" y="62" font-size="9">iiq_r_valid</text>')
    b.append(box(100, 78, 480, 72,
                 "s0[3:0] valid-bit 占用掩码\n"
                 "4×IIQ_WIDTH 数据 RAM（PC/NPC/ctrl/imm/pred/…）\n"
                 "pop 后 kv_iiq_wrap 再跑 kv_dec → ii_i0/i1_ctrl", "panel", 11))
    (OUT / "iiq.svg").write_text(wrap_svg("\n".join(b), w, h), encoding="utf-8")


STAGES = ["IF", "IC", "ID", "IS", "EX", "MM", "LX", "WB"]


def t(cols, data: dict, stalls=None, title=""):
    cells = {(r, c): v for r, row in data.items() for c, v in row.items()}
    return timing_svg(cols, STAGES, cells, stalls=stalls or set(), title=title)


TIMINGS = {
    "t00": (["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"], {
        "IF": {"C0": "A"}, "IC": {"C1": "A"}, "ID": {"C2": "A"}, "IS": {"C3": "A"},
        "EX": {"C4": "A", "C5": "alu0/bru0"}, "MM": {"C5": "A", "C6": "分支判定"},
        "LX": {"C6": "A", "C7": "结果/LS"}, "WB": {"C7": "A", "C8": "rf_we"},
    }),
    "t01": (["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9"], {
        "IF": {"C0": "A", "C1": "B", "C2": "C", "C3": "D"},
        "IC": {"C1": "A", "C2": "B", "C3": "C", "C4": "D"},
        "ID": {"C2": "A,B", "C3": "C,D", "C4": "A,B", "C5": "C,D"},
        "IS": {"C3": "A,B", "C4": "C,D", "C5": "A,B", "C6": "C,D"},
        "EX": {"C4": "A,B", "C5": "C,D", "C6": "A,B", "C7": "C,D"},
        "MM": {"C5": "A,B", "C6": "C,D", "C7": "A,B", "C8": "C,D"},
        "LX": {"C6": "A,B", "C7": "C,D", "C8": "A,B", "C9": "C,D"},
        "WB": {"C7": "A,B", "C8": "C,D", "C9": "A,B"},
    }),
    "t02": (["C3", "C4", "C5", "C6"], {
        "IS": {"C3": "A", "C5": "B\nbyp[1]"},
        "EX": {"C4": "A→ex_rd1", "C6": "B"},
    }),
    "t03": (["C3", "C4", "C5", "C6", "C7", "C8", "C9"], {
        "IS": {"C3": "A", "C6": "B\nlate", "C7": "B"},
        "EX": {"C4": "A\nls_req", "C8": "B\n[149]"},
        "MM": {"C5": "A", "C9": "B"},
        "LX": {"C6": "A\nls_resp", "C9": "B\nalu2"},
        "WB": {"C9": "B\nrf_we"},
    }),
    "t04": (["C3", "C4", "C5", "C6", "C7", "C8"], {
        "IS": {"C3": "A", "C4": "B", "C5": "stall", "C6": "B"},
        "EX": {"C4": "A", "C7": "B"},
        "MM": {"C5": "A"}, "LX": {"C6": "A"},
    }, {("IS", "C5")}),
    "t05": (["C3", "C4", "C5", "C6", "C7"], {
        "IS": {"C3": "A,B"}, "EX": {"C4": "A,B"},
        "MM": {"C5": "A"}, "LX": {"C6": "A\nls_resp", "C7": "B"},
    }),
    "t06": (["C4", "C5", "C6", "C7", "C8", "C9"], {
        "EX": {"C4": "A\nbru0"}, "MM": {"C5": "A\nmispred"},
        "IF": {"C7": "redirect"}, "IS": {"C8": "A'"},
    }),
    "t07": (["C5", "C6", "C7", "C8", "C9"], {
        "EX": {"C5": "A"}, "MM": {"C6": "A"},
        "LX": {"C7": "A\nbru2"}, "WB": {"C8": "A"},
        "IF": {"C9": "redirect"},
    }),
    "t08": (["C4", "C5", "C6", "C7", "C8", "C9"], {
        "IS": {"C4": "A", "C5": "B", "C7": "B停", "C9": "B"},
        "EX": {"C5": "A", "C6": "B", "C8": "A,B hold"},
        "MM": {"C6": "A", "C7": "B", "C9": "A,B"},
        "LX": {"C7": "A══", "C9": "A\nls_resp"},
    }, {("IS", "C7")}),
    "t09": (["C4", "C5", "C6", "C7", "C8", "C9", "C10"], {
        "EX": {"C4": "LD\nls_req"}, "MM": {"C5": "LD"},
        "LX": {"C6": "LD══", "C7": "LD\nls_resp"},
        "WB": {"C8": "LD\nrf_we"},
    }),
    "t10": (["C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11"], {
        "EX": {"C4": "DIV\nmdu_req"}, "MM": {"C5": "DIV"},
        "LX": {"C6": "DIV══", "C7": "DIV\nresp"},
        "WB": {"C8": "DIV\nrf_we"},
    }),
    "t11": (["C3", "C4"], {
        "IS": {"C3": "A\n仅发A", "C4": "B"},
    }, {("IS", "C3")}),
    "t12": (["EX/MM", "IS", "MM"], {
        "EX": {"EX/MM": "A nbload"}, "IS": {"IS": "B\nnbload hz"},
        "MM": {"MM": "replay?"},
    }),
    "t13": (["C6"], {
        "EX": {"C6": "D early"}, "MM": {"C6": "C"},
        "LX": {"C6": "B late"}, "WB": {"C6": "A"},
    }),
    "t14": (["IS", "EX"], {
        "IS": {"IS": "B\nno EX fwd"}, "EX": {"EX": "A"},
    }),
    "t15": (["C0", "C1", "C2", "C3", "C4"], {
        "IF": {"C0": "*", "C1": "*", "C2": "stall"},
        "IC": {"C1": "*", "C2": "*"},
        "FQ": {"C2": "[满]"},
        "ID": {"C3": "stall"},
    }),
    "t16": (["C3", "C4", "C5", "C6"], {
        "ID": {"C3": "push A,B", "C4": "push C,D"},
        "IS": {"C4": "A,B stall", "C6": "pop A,B"},
        "IIQ": {"C4": "[A,B,C,D]"},
    }, {("IS", "C4")}),
    "t17": (["C7", "C8", "C9"], {
        "LX": {"C7": "A", "C8": "B"},
        "WB": {"C8": "A\ntrap", "C9": "B kill"},
        "EX": {"C9": "C kill"},
        "IS": {"C9": "flush"},
    }),
}


def gen_timings():
    for name, spec in TIMINGS.items():
        if len(spec) == 2:
            cols, data = spec
            stalls = set()
        else:
            cols, data, stalls = spec
        rows = list(data.keys())
        if rows != STAGES:
            # custom row order from dict keys
            pass
        cells = {(r, c): v for r, row in data.items() for c, v in row.items() if v}
        svg = timing_svg(cols, rows, cells, stalls=stalls)
        (OUT / f"{name}.svg").write_text(svg, encoding="utf-8")


def main():
    OUT.mkdir(exist_ok=True)
    gen_data_ctrl()
    gen_fetch()
    gen_block()
    gen_fq()
    gen_iiq()
    gen_timings()
    print(f"Wrote SVGs to {OUT}/")


if __name__ == "__main__":
    main()
