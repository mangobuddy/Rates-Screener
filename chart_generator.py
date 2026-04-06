"""
Chart generation: yield curve PNG images for Telegram.
Single government bond curve + overnight rate reference line.
"""
import io
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from datetime import datetime
from src.curve_builder import interpolate_curve

# Palette
C = {
    "curve": "#1D4ED8", "dots": "#1E40AF", "fill": "#DBEAFE",
    "overnight": "#059669", "grid": "#E5E7EB", "bg": "#FFFFFF",
    "text": "#111827", "sub": "#6B7280",
}


def generate_curve_chart(data: dict) -> io.BytesIO:
    """Render a yield curve chart → PNG BytesIO buffer."""
    cfg = data["config"]
    ccy = data["currency"]
    ovn = data.get("overnight", {})
    crv = data.get("curve", {})

    has_crv = crv and len(crv.get("years", [])) >= 2
    has_ovn = ovn and ovn.get("rate") is not None

    if not has_crv and not has_ovn:
        return _empty_chart(ccy, cfg)

    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=150)
    fig.patch.set_facecolor(C["bg"]); ax.set_facecolor(C["bg"])

    xmax = 1

    # ── Government bond curve ──
    if has_crv:
        xr, yr = crv["years"], crv["yields"]
        xs, ys = interpolate_curve(xr, yr)
        ax.plot(xs, ys, color=C["curve"], linewidth=2.5, label=cfg["bond"], zorder=3)
        ax.fill_between(xs, ys, alpha=0.07, color=C["curve"], zorder=1)
        ax.scatter(xr, yr, color=C["dots"], s=45, zorder=4, edgecolors="white", linewidths=1.5)
        # Annotate every data point
        for x, y, t in zip(xr, yr, crv["tenors"]):
            ax.annotate(f"{t}\n{y:.2f}%", (x, y), textcoords="offset points",
                        xytext=(0, 13), fontsize=7, color=C["dots"], ha="center",
                        fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec=C["curve"], alpha=0.85, lw=0.5))
        xmax = max(xr) * 1.05

    # ── Overnight rate reference ──
    if has_ovn:
        rate = ovn["rate"]
        ax.axhline(y=rate, color=C["overnight"], lw=1.5, ls=":", alpha=0.7, zorder=2)
        ax.text(xmax * 0.02, rate,
                f"  {ovn['name']} = {rate:.4f}%",
                color=C["overnight"], fontsize=9, fontweight="bold", va="bottom",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=C["overnight"], alpha=0.9))

    # ── Labels ──
    ax.set_xlabel("Maturity (Years)", fontsize=11, color=C["text"], fontweight="medium")
    ax.set_ylabel("Yield (%)", fontsize=11, color=C["text"], fontweight="medium")

    date_str = crv.get("date") or ovn.get("date") or ""
    date_show = date_str[:10] if date_str and len(date_str) >= 10 else datetime.now().strftime("%Y-%m-%d")

    ax.set_title(f"{cfg['flag']}  {ccy} — {cfg['bond']} Yield Curve",
                 fontsize=14, fontweight="bold", color=C["text"], pad=15)
    ax.text(0.5, 1.02, f"As of {date_show}  ·  {cfg['country']}",
            transform=ax.transAxes, ha="center", fontsize=9, color=C["sub"])

    # ── Style ──
    ax.grid(True, alpha=0.3, color=C["grid"], lw=0.8)
    for sp in ["top", "right"]: ax.spines[sp].set_visible(False)
    for sp in ["left", "bottom"]: ax.spines[sp].set_color(C["grid"])
    ax.tick_params(colors=C["sub"], labelsize=9)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
    if has_crv:
        ax.set_xlim(0, xmax)

    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(loc="best", fontsize=9, framealpha=0.9, edgecolor=C["grid"])

    fig.text(0.98, 0.01, "Source: Central Banks / FRED / ECB",
             ha="right", fontsize=7, color=C["sub"], style="italic")
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=C["bg"])
    plt.close(fig)
    buf.seek(0)
    return buf


def _empty_chart(ccy, cfg):
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=150)
    fig.patch.set_facecolor(C["bg"]); ax.set_facecolor(C["bg"])
    ax.text(0.5, 0.5, f"No data available for {ccy} ({cfg['name']})",
            transform=ax.transAxes, ha="center", va="center", fontsize=16, color=C["sub"])
    ax.set_xlim(0, 30); ax.set_ylim(0, 5)
    for sp in ["top", "right"]: ax.spines[sp].set_visible(False)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=C["bg"])
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_summary_text(data: dict) -> str:
    """Plain-text summary of overnight rate + yield curve for Telegram."""
    if data.get("error"):
        return f"❌ {data['error']}"

    cfg = data["config"]
    ccy = data["currency"]
    ovn = data.get("overnight", {})
    crv = data.get("curve", {})

    lines = []
    lines.append(f"{'═'*34}")
    lines.append(f" {cfg['flag']}  {ccy} — {cfg['name']}")
    lines.append(f" {cfg['country']}")
    lines.append(f"{'═'*34}")

    # Overnight
    if ovn.get("rate") is not None:
        lines.append(f"\n📌 {ovn['name']}: {ovn['rate']:.4f}%")
        if ovn.get("date"): lines.append(f"   ({ovn['date'][:10]})")
    else:
        lines.append(f"\n📌 {cfg['overnight']}: N/A")

    # Curve
    lines.append(f"\n📊 {cfg['bond']} Yields:")
    if crv and crv.get("tenors"):
        lines.append(f"   {'Tenor':<6} {'Yield':>8}")
        lines.append(f"   {'─'*16}")
        for t, y in zip(crv["tenors"], crv["yields"]):
            lines.append(f"   {t:<6} {y:>7.3f}%")
        if crv.get("date"):
            lines.append(f"   ({crv['date'][:10]})")
    else:
        lines.append("   No data available")

    lines.append(f"\n{'─'*34}")
    lines.append("Src: Central Banks / FRED / ECB")
    return "\n".join(lines)
