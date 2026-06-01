"""
Generate architecture diagram PNG for Text-to-Insights.
Run: python docs/generate_diagram.py
Output: docs/architecture.png
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import os

OUTPUT = os.path.join(os.path.dirname(__file__), "architecture.png")

# ── Colour palette ─────────────────────────────────────────────────────────────
C = {
    "user":       "#1A73E8",   # Google blue
    "gateway":    "#1557A0",   # dark blue
    "registry":   "#2E7D32",   # green
    "retrieval":  "#00838F",   # teal
    "mapper":     "#00695C",   # dark teal
    "generator":  "#6A1B9A",   # purple
    "validator":  "#AD1457",   # pink
    "executor":   "#BF360C",   # deep orange
    "formatter":  "#E65100",   # orange
    "ollama":     "#4A148C",   # deep purple
    "metricsdb":  "#1B5E20",   # dark green
    "bg":         "#F8F9FA",
    "arrow":      "#455A64",
    "border":     "#CFD8DC",
    "pipeline_bg":"#E3F2FD",
    "text_white": "#FFFFFF",
    "text_dark":  "#212121",
}


def box(ax, x, y, w, h, label, sublabel=None, color="#1A73E8", fontsize=9, radius=0.015):
    fancy = FancyBboxPatch(
        (x - w/2, y - h/2), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        facecolor=color, edgecolor="white", linewidth=1.5, zorder=3
    )
    ax.add_patch(fancy)
    if sublabel:
        ax.text(x, y + 0.012, label, ha="center", va="center",
                fontsize=fontsize, fontweight="bold", color="white", zorder=4)
        ax.text(x, y - 0.014, sublabel, ha="center", va="center",
                fontsize=6.5, color="#E0E0E0", zorder=4)
    else:
        ax.text(x, y, label, ha="center", va="center",
                fontsize=fontsize, fontweight="bold", color="white", zorder=4)


def arrow(ax, x1, y1, x2, y2, label=None, color="#455A64", lw=1.5):
    ax.annotate("",
        xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle="-|>", color=color, lw=lw,
                        connectionstyle="arc3,rad=0.0"),
        zorder=2)
    if label:
        mx, my = (x1+x2)/2, (y1+y2)/2
        ax.text(mx+0.01, my, label, fontsize=6.5, color=color,
                ha="left", va="center", style="italic", zorder=5)


def curved_arrow(ax, x1, y1, x2, y2, rad=0.3, color="#455A64", lw=1.5):
    ax.annotate("",
        xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle="-|>", color=color, lw=lw,
                        connectionstyle=f"arc3,rad={rad}"),
        zorder=2)


fig, ax = plt.subplots(figsize=(18, 13))
fig.patch.set_facecolor(C["bg"])
ax.set_facecolor(C["bg"])
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")

# ── Title ──────────────────────────────────────────────────────────────────────
ax.text(0.5, 0.965, "Text-to-Insights — System Architecture",
        ha="center", va="center", fontsize=16, fontweight="bold", color=C["text_dark"])
ax.text(0.5, 0.945, "Enterprise Natural Language Query System for Telecom OSS/BSS Metrics  |  100% On-Premise  |  Zero External API Cost",
        ha="center", va="center", fontsize=9, color="#607D8B")

# ── Pipeline background ────────────────────────────────────────────────────────
pipe_bg = FancyBboxPatch((0.30, 0.08), 0.40, 0.82,
    boxstyle="round,pad=0,rounding_size=0.02",
    facecolor=C["pipeline_bg"], edgecolor="#90CAF9", linewidth=1.5,
    linestyle="--", zorder=1)
ax.add_patch(pipe_bg)
ax.text(0.50, 0.895, "LangGraph Pipeline", ha="center", va="center",
        fontsize=9, color="#1565C0", fontweight="bold", zorder=2)

# ── User / Browser ─────────────────────────────────────────────────────────────
box(ax, 0.10, 0.75, 0.16, 0.07, "Business User", "Streamlit :8501", C["user"], 9)

# ── API Gateway ────────────────────────────────────────────────────────────────
box(ax, 0.50, 0.84, 0.32, 0.065, "Module 8 — API Gateway",
    "FastAPI · JWT Auth · Rate Limit · Audit Log", C["gateway"], 9)

# ── Schema Registry ────────────────────────────────────────────────────────────
box(ax, 0.12, 0.45, 0.16, 0.07, "Module 1", "Schema Registry", C["registry"], 8.5)

# ── Pipeline modules (vertical stack) ─────────────────────────────────────────
MODULE_X = 0.50
boxes = [
    (0.74, "Module 2 — Table Retrieval",  "+10/+5/+3/+4 Scoring",  C["retrieval"]),
    (0.63, "Module 3 — Value Mapper",     "Dallas→DFW  active→A",  C["mapper"]),
    (0.52, "Module 4 — SQL Generator",    "Ollama · sqlcoder",       C["generator"]),
    (0.41, "Module 5 — SQL Validator",    "Rules 1-5 · Retry Loop",  C["validator"]),
    (0.30, "Module 6 — SQL Executor",     "Read-only Pool · 30s cap",C["executor"]),
    (0.19, "Module 7 — Report Formatter", "Ollama · mistral",        C["formatter"]),
]
for y, label, sub, color in boxes:
    box(ax, MODULE_X, y, 0.32, 0.065, label, sub, color, 8.5)

# ── Ollama ─────────────────────────────────────────────────────────────────────
box(ax, 0.85, 0.52, 0.16, 0.07, "Ollama SLM", "sqlcoder · mistral", C["ollama"], 8.5)

# ── Metrics DB ────────────────────────────────────────────────────────────────
box(ax, 0.85, 0.30, 0.16, 0.07, "Metrics Server",
    "Telecom OSS/BSS DB", C["metricsdb"], 8.5)

# ── Registry DB ───────────────────────────────────────────────────────────────
box(ax, 0.12, 0.30, 0.16, 0.07, "Registry DB",
    "SQLite / PostgreSQL", C["registry"], 8.5)

# ── Audit DB ──────────────────────────────────────────────────────────────────
box(ax, 0.85, 0.84, 0.16, 0.065, "Audit Log", "SQLite", "#546E7A", 8.5)

# ── Arrows ────────────────────────────────────────────────────────────────────
# User → Gateway
arrow(ax, 0.18, 0.75, 0.34, 0.84, "Question", "#1A73E8", 1.8)

# Gateway → Table Retrieval (entry point)
arrow(ax, 0.50, 0.808, 0.50, 0.773, color=C["arrow"])

# Pipeline vertical flow
for i in range(len(boxes)-1):
    y1 = boxes[i][0] - 0.0325
    y2 = boxes[i+1][0] + 0.0325
    arrow(ax, MODULE_X, y1, MODULE_X, y2, color=C["arrow"])

# Schema Registry ↔ Module 2 (table retrieval reads registry)
arrow(ax, 0.20, 0.45, 0.34, 0.74, color=C["registry"], lw=1.2)
# Registry DB ↔ Schema Registry
arrow(ax, 0.12, 0.337, 0.12, 0.413, color=C["registry"], lw=1.2)

# SQL Generator → Ollama
arrow(ax, 0.66, 0.52, 0.77, 0.52, "generate SQL", C["ollama"], 1.5)
# Ollama → SQL Generator (response)
curved_arrow(ax, 0.77, 0.515, 0.66, 0.515, rad=-0.4, color=C["ollama"], lw=1.2)

# Report Formatter → Ollama
curved_arrow(ax, 0.66, 0.19, 0.77, 0.49, rad=-0.15, color=C["ollama"], lw=1.2)
# Ollama → Report Formatter
curved_arrow(ax, 0.77, 0.485, 0.66, 0.185, rad=0.15, color=C["ollama"], lw=1.2)

# SQL Executor → Metrics DB
arrow(ax, 0.66, 0.30, 0.77, 0.30, "SQL query", C["metricsdb"], 1.5)
# Metrics DB → SQL Executor (results)
curved_arrow(ax, 0.77, 0.295, 0.66, 0.295, rad=-0.4, color=C["metricsdb"], lw=1.2)

# Gateway → Audit Log
arrow(ax, 0.66, 0.84, 0.77, 0.84, "log", "#546E7A", 1.2)

# Report Formatter → output
arrow(ax, 0.50, 0.157, 0.50, 0.10, color=C["formatter"])

# ── Output box ─────────────────────────────────────────────────────────────────
out = FancyBboxPatch((0.30, 0.03), 0.40, 0.065,
    boxstyle="round,pad=0,rounding_size=0.012",
    facecolor="#F3E5F5", edgecolor="#CE93D8", linewidth=1.5, zorder=3)
ax.add_patch(out)
ax.text(0.50, 0.063, "Narrative Report  +  Data Table  +  Key Insights  -->  Back to Streamlit UI",
        ha="center", va="center", fontsize=8.5, color="#4A148C",
        fontweight="bold", zorder=4)

# ── Validator retry annotation ────────────────────────────────────────────────
ax.annotate("",
    xy=(0.345, 0.52), xytext=(0.345, 0.41),
    arrowprops=dict(arrowstyle="-|>", color=C["validator"], lw=1.2,
                    connectionstyle="arc3,rad=-0.4"),
    zorder=2)
ax.text(0.275, 0.465, "retry\n(max 2×)", ha="center", va="center",
        fontsize=7, color=C["validator"], style="italic", zorder=5)

# ── Legend ─────────────────────────────────────────────────────────────────────
legend_items = [
    (C["user"],      "User / UI"),
    (C["gateway"],   "API Gateway"),
    (C["registry"],  "Schema Registry"),
    (C["retrieval"], "Table Retrieval"),
    (C["mapper"],    "Value Mapper"),
    (C["generator"], "SQL Generator"),
    (C["validator"], "SQL Validator"),
    (C["executor"],  "SQL Executor"),
    (C["formatter"], "Report Formatter"),
    (C["ollama"],    "Ollama SLM"),
    (C["metricsdb"], "Metrics DB"),
]
handles = [mpatches.Patch(facecolor=c, label=l, edgecolor="white") for c, l in legend_items]
ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.0, 0.0),
          ncol=2, fontsize=7.5, framealpha=0.9, edgecolor=C["border"],
          facecolor="white", title="Components", title_fontsize=8)

plt.tight_layout(pad=0.5)
plt.savefig(OUTPUT, dpi=150, bbox_inches="tight", facecolor=C["bg"])
plt.close()
print(f"Diagram saved to {OUTPUT}")
