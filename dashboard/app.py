"""Streamlit dashboard: streamlit run dashboard/app.py"""
import re
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import report  # noqa: E402
from src.report import CATEGORIES, COLORS  # noqa: E402

st.set_page_config(page_title="Active vs index funds", layout="wide")
st.markdown("""
<style>
  .block-container {max-width: 1150px; padding-top: 2.2rem;}
  .big-number {font-size: 5.2rem; font-weight: 700; line-height: 1; color: #2a78d6; letter-spacing: -0.02em;}
  .stat {font-size: 2rem; font-weight: 650; line-height: 1.1;}
  .stat-label, .big-label {color: #52514e; font-size: 0.95rem; margin-top: 0.35rem;}
  .stat-label {margin-bottom: 1.4rem;}
  .big-label {font-size: 1.05rem; max-width: 34rem;}
  .kicker {color: #52514e; text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.78rem;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load(name: str) -> pd.DataFrame:
    return report.view(name)


@st.cache_data(show_spinner=False)
def beat_over_time(years: int) -> pd.DataFrame:
    return report.beat_share_over_time(years)


@st.cache_data(show_spinner=False)
def excess_series(code: int) -> pd.DataFrame:
    return report.fund_excess_series(code)


def fund_name(scheme_name: str) -> str:
    """'HDFC Flexi Cap Fund - Direct Plan - Growth Option' -> 'HDFC Flexi Cap Fund'. Only splits at a
    hyphen, so 'Nippon India Growth Fund - Direct Plan' keeps 'Growth' in its name."""
    name = re.split(r"\s*-\s*(?=(?:direct|regular|growth)\b)", scheme_name, maxsplit=1, flags=re.I)[0]
    return name.strip(" -.")


def style(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["surface"],
        font=dict(color=COLORS["text"], size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        hoverlabel=dict(bgcolor="white", font_color=COLORS["text"]),
    )
    fig.update_xaxes(showgrid=False, linecolor=COLORS["grid"], tickfont_color=COLORS["text_secondary"],
                     automargin=True)
    fig.update_yaxes(gridcolor=COLORS["grid"], zeroline=False, tickfont_color=COLORS["text_secondary"],
                     automargin=True, ticksuffix="  ")
    return fig


def chart(fig: go.Figure, caption: str) -> None:
    st.plotly_chart(fig, use_container_width=True, theme=None, config={"displayModeBar": False})
    st.caption(caption)


def pct(x, signed=False, digits=0):
    if pd.isna(x):
        return "–"
    return f"{x:+.{digits}%}" if signed else f"{x:.{digits}%}"


def lakh(x):
    return "–" if pd.isna(x) else f"₹{x / 1e5:.2f} lakh"


# ---------------------------------------------------------------- page 1
def headline_page():
    h = load("headline").iloc[0]
    st.markdown('<div class="kicker">Indian equity mutual funds · data to '
                f'{pd.Timestamp(h.data_as_of):%d %b %Y}</div>', unsafe_allow_html=True)
    st.title("Do active funds beat index funds after costs?")

    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.markdown(f'<div class="big-number">{h.direct_share_beating_5y:.0%}</div>'
                    f'<div class="big-label">of active funds beat their index fund over a typical 5-year window, '
                    f'comparing direct plan to direct plan ({h.direct_funds_5y:.0f} funds). '
                    f'Barely better than a coin flip.</div>', unsafe_allow_html=True)
    with right:
        a, b = st.columns(2)
        a.markdown(f'<div class="stat" style="color:{COLORS["regular"]}">{h.regular_share_beating_5y:.0%}</div>'
                   '<div class="stat-label">do it in the regular plan, after the distributor commission</div>',
                   unsafe_allow_html=True)
        b.markdown(f'<div class="stat">{pct(h.direct_median_excess_5y, True, 2)}</div>'
                   '<div class="stat-label">median fund\'s yearly edge over the index (direct)</div>',
                   unsafe_allow_html=True)
        a.markdown(f'<div class="stat">{pct(h.median_annual_gap, digits=2)}</div>'
                   '<div class="stat-label">a year lost in the regular plan vs direct (median)</div>',
                   unsafe_allow_html=True)
        b.markdown(f'<div class="stat">{lakh(h.median_sip_rupee_gap)}</div>'
                   '<div class="stat-label">lost on a ₹10,000/month SIP over 10 years (median)</div>',
                   unsafe_allow_html=True)

    st.divider()
    c1, c2 = st.columns([1, 1])
    window = c1.segmented_control("Rolling window", [3, 5], default=5, format_func=lambda y: f"{y} years")
    metric = c2.segmented_control(
        "Measure", ["share_funds_beating", "pooled_beat_rate"], default="share_funds_beating",
        format_func=lambda m: {"share_funds_beating": "Share of funds", "pooled_beat_rate": "Beat rate (all windows)"}[m])
    window, metric = window or 5, metric or "share_funds_beating"

    cs = load("category_summary")
    cs = cs[cs.window_years == window]
    order = CATEGORIES + ["All"]
    fig = go.Figure()
    for plan in ("direct", "regular"):
        s = cs[cs.plan_type == plan].set_index("category").reindex(order)
        fig.add_bar(y=order, x=s[metric], orientation="h", name=f"{plan.title()} plan", marker_color=COLORS[plan],
                    text=[pct(v) for v in s[metric]], textposition="outside", cliponaxis=False,
                    customdata=s[["n_funds", "median_fund_excess"]],
                    hovertemplate="%{y}: %{x:.0%}<br>%{customdata[0]} funds, median excess "
                                  "%{customdata[1]:+.2%}/yr<extra>" + plan.title() + "</extra>")
    fig.add_vline(x=0.5, line_dash="dash", line_color=COLORS["index"], line_width=1,
                  annotation_text="50%", annotation_position="top right",
                  annotation_font_color=COLORS["text_secondary"])
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.06)
    fig.update_xaxes(tickformat=".0%", range=[0, 1], showgrid=True, gridcolor=COLORS["grid"])
    fig.update_yaxes(autorange="reversed", showgrid=False)
    what = ("share of funds whose median rolling return beat the index fund" if metric == "share_funds_beating"
            else "share of all monthly fund-windows that beat the index fund")
    chart(style(fig, 380), f"By category, {window}-year windows: {what}. Dashed line = 50%.")

    st.subheader("It depends on when you look")
    t = beat_over_time(3)
    cat = st.segmented_control("Category", CATEGORIES, default="Large Cap", key="time_cat") or "Large Cap"
    fig = go.Figure()
    for plan in ("direct", "regular"):
        s = t[(t.category == cat) & (t.plan_type == plan)]
        fig.add_scatter(x=s.end_date, y=s.share_beating, mode="lines", name=f"{plan.title()} plan",
                        line=dict(color=COLORS[plan], width=2.5),
                        hovertemplate="%{x|%b %Y}: %{y:.0%} of funds<extra>" + plan.title() + "</extra>")
    fig.add_hline(y=0.5, line_dash="dash", line_color=COLORS["index"], line_width=1)
    fig.update_yaxes(tickformat=".0%", range=[0, 1.02])
    fig.update_layout(hovermode="x unified")
    chart(style(fig, 340), f"{cat}: share of funds beating the index fund in each rolling 3-year window, "
                           "by the month the window ends.")

    with st.expander("Survivorship and other limitations"):
        sv = load("survivorship")
        sv = sv[(sv.plan_type == "direct") & (sv.category == "All")].iloc[0]
        st.markdown(f"""
- Of **{sv.schemes_at_start}** direct-plan funds alive on {pd.Timestamp(sv.window_start):%d %b %Y},
  **{sv.closed_or_merged}** have since closed or merged. They are included up to the day they stop,
  but funds that closed before SEBI's 2018 recategorisation can't be categorised and are missing.
  This flatters active funds.
- Flexi Cap and Mid Cap benchmarks (Nifty 500 and Midcap 150 index funds) start in Sep 2019, so
  their 5-year windows only cover Sep 2024 onward.
- Large Cap funds are compared with a Nifty 50 index fund; part of their edge is a mid-cap tilt.
""")


# ---------------------------------------------------------------- page 2
def report_card_page():
    lb = load("fund_leaderboard")
    lb = lb.assign(fund=lb.scheme_name.map(fund_name))
    st.title("Fund report card")
    c1, c2, c3 = st.columns([1, 2.2, 1])
    cat = c1.selectbox("Category", CATEGORIES)
    funds = (lb[lb.category == cat].sort_values(["is_active", "fund"], ascending=[False, True])
             .drop_duplicates("fund").fund.tolist())
    fund = c2.selectbox("Fund", funds, help="Funds that have closed or merged are listed after active ones.")
    plan = c3.radio("Plan", ["direct", "regular"], horizontal=True, format_func=str.title)
    rows = lb[(lb.category == cat) & (lb.fund == fund)]
    sel = rows[rows.plan_type == plan]
    if sel.empty:
        st.info(f"No {plan} plan for this fund in the data.")
        return
    f = sel.iloc[0]
    status = "active" if f.is_active else f"closed or merged (last NAV {f.last_nav_date:%d %b %Y})"
    st.caption(f"{f.scheme_name} · {f.fund_house} · scheme code {f.scheme_code} · {status}")

    window = st.segmented_control("Rolling window", [1, 3, 5], default=3, format_func=lambda y: f"{y} years",
                                  key="rc_window") or 3
    ex = excess_series(int(f.scheme_code))
    ex = ex[ex.window_years == window]
    if ex.empty:
        st.info(f"Not enough history for a {window}-year comparison with the index fund.")
    else:
        colors = [COLORS["positive"] if v >= 0 else COLORS["negative"] for v in ex.excess_return]
        fig = go.Figure(go.Bar(
            x=ex.end_date, y=ex.excess_return, marker_color=colors, marker_line_width=0,
            customdata=ex[["fund_cagr", "bench_cagr"]],
            hovertemplate="%{x|%b %Y}<br>Excess %{y:+.2%}/yr<br>Fund %{customdata[0]:.2%} · "
                          "Index fund %{customdata[1]:.2%}<extra></extra>"))
        fig.add_hline(y=0, line_color=COLORS["text"], line_width=1)
        fig.update_yaxes(tickformat="+.0%")
        fig.update_layout(bargap=0.15)
        beat = (ex.excess_return > 0).mean()
        chart(style(fig, 340), f"Rolling {window}-year CAGR minus the {cat} index fund's, for each window ending in "
                               f"the month shown. Blue = beat the index ({beat:.0%} of windows), red = lagged.")

    st.subheader("Metrics")
    table = rows.set_index("plan_type").reindex(["direct", "regular"])
    metrics = pd.DataFrame({
        "3-yr beat rate": table.beat_rate_3y.map(pct),
        "3-yr median excess": table.median_excess_3y.map(lambda v: pct(v, True, 2)),
        "5-yr beat rate": table.beat_rate_5y.map(pct),
        "5-yr median excess": table.median_excess_5y.map(lambda v: pct(v, True, 2)),
        "CAGR (5 yr)": table.cagr_trailing.map(lambda v: pct(v, digits=1)),
        "Volatility": table.volatility.map(lambda v: pct(v, digits=1)),
        "Sharpe": table.sharpe.map(lambda v: "–" if pd.isna(v) else f"{v:.2f}"),
        "Sortino": table.sortino.map(lambda v: "–" if pd.isna(v) else f"{v:.2f}"),
        "Max drawdown": table.max_drawdown.map(lambda v: pct(v, digits=1)),
    }).set_axis(["Direct", "Regular"]).T
    st.dataframe(metrics, use_container_width=True)
    st.caption("Beat rate = share of rolling windows in which the fund beat its index fund. Risk metrics cover the "
               "trailing 5 years (risk-free rate 6.5%); blank where the fund lacks 5 full years.")

    st.subheader("Direct vs regular")
    gap = load("direct_regular_gap")
    g = gap[gap.direct_code.isin(rows.scheme_code)]
    if g.empty:
        st.info("No direct/regular pair with at least a year of common, current history.")
        return
    g = g.iloc[0]
    a, b, c = st.columns(3)
    a.metric("Regular plan costs", f"{g.annual_gap:.2%} a year", help=f"Over {g.years_compared:.1f} years of common history")
    if pd.isna(g.sip_rupee_gap):
        b.metric("SIP gap", "–", help="Needs 10 years of history in both plans")
        c.metric("Years compared", f"{g.years_compared:.1f}")
        return
    b.metric("10-yr SIP: direct ends ahead by", lakh(g.sip_rupee_gap))
    c.metric("Invested", lakh(g.sip_invested))
    fig = go.Figure(go.Bar(
        y=["Direct plan", "Regular plan"], x=[g.sip_direct_value, g.sip_regular_value], orientation="h",
        marker_color=[COLORS["direct"], COLORS["regular"]], text=[lakh(g.sip_direct_value), lakh(g.sip_regular_value)],
        textposition="outside", cliponaxis=False, hovertemplate="%{y}: ₹%{x:,.0f}<extra></extra>"))
    fig.add_vline(x=g.sip_invested, line_dash="dash", line_color=COLORS["text_secondary"], line_width=1.5)
    fig.update_layout(bargap=0.45)
    fig.update_xaxes(tickprefix="₹", tickformat=",.0f", showgrid=True, gridcolor=COLORS["grid"],
                     range=[0, max(g.sip_direct_value, g.sip_regular_value) * 1.18])
    fig.update_yaxes(autorange="reversed")
    chart(style(fig, 230), "Value today of ₹10,000 invested on the first trading day of each of the last 120 months. "
                           "Dashed line = amount invested.")


# ---------------------------------------------------------------- page 3
def leaderboard_page():
    lb = load("fund_leaderboard")
    st.title("Leaderboard")
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    cats = c1.multiselect("Category", CATEGORIES, default=CATEGORIES)
    plan = c2.radio("Plan", ["direct", "regular"], horizontal=True, format_func=str.title)
    min_windows = c3.number_input("Min 5-yr windows", min_value=0, max_value=120, value=12, step=6,
                                  help="Funds with fewer monthly 5-year windows have too little history to rank.")
    active_only = c4.toggle("Active funds only", value=True)
    df = lb[lb.category.isin(cats) & (lb.plan_type == plan) & (lb.windows_5y.fillna(0) >= min_windows)]
    if active_only:
        df = df[df.is_active]
    df = df.assign(fund=df.scheme_name.map(fund_name)).sort_values("median_excess_5y", ascending=False)
    pct_cols = ["median_excess_5y", "beat_rate_5y", "median_excess_3y", "beat_rate_3y", "cagr_trailing",
                "volatility", "max_drawdown", "direct_regular_gap"]
    df[pct_cols] = df[pct_cols] * 100  # column formats below print these as percentages
    cols = {
        "fund": st.column_config.TextColumn("Fund", width="large"),
        "category": "Category",
        "median_excess_5y": st.column_config.NumberColumn("5-yr median excess", format="%+.2f%%"),
        "beat_rate_5y": st.column_config.NumberColumn("5-yr beat rate", format="%.0f%%"),
        "windows_5y": st.column_config.NumberColumn("5-yr windows"),
        "median_excess_3y": st.column_config.NumberColumn("3-yr median excess", format="%+.2f%%"),
        "beat_rate_3y": st.column_config.NumberColumn("3-yr beat rate", format="%.0f%%"),
        "cagr_trailing": st.column_config.NumberColumn("CAGR (5 yr)", format="%.1f%%"),
        "volatility": st.column_config.NumberColumn("Volatility", format="%.1f%%"),
        "sharpe": st.column_config.NumberColumn("Sharpe", format="%.2f"),
        "sortino": st.column_config.NumberColumn("Sortino", format="%.2f"),
        "max_drawdown": st.column_config.NumberColumn("Max drawdown", format="%.1f%%"),
        "direct_regular_gap": st.column_config.NumberColumn("Regular plan cost/yr", format="%.2f%%"),
    }
    st.dataframe(df[list(cols)], column_config=cols, hide_index=True, use_container_width=True, height=620)
    st.caption(f"{len(df)} funds. Click a column header to sort. Excess and beat rate compare each fund with its "
               "category's index fund over rolling monthly windows; risk metrics cover the trailing 5 years.")


pg = st.navigation([
    st.Page(headline_page, title="Headline", default=True),
    st.Page(report_card_page, title="Fund report card", url_path="report-card"),
    st.Page(leaderboard_page, title="Leaderboard", url_path="leaderboard"),
])
pg.run()
