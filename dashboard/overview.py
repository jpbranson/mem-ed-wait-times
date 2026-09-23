"""The opening all-hospital chart, using the prepared M1 history."""

import html
from datetime import timedelta

import plotly.graph_objects as go

from edwait.data import LOCAL_TIMEZONE, timestamp
from zoneinfo import ZoneInfo

COLORS = ["#70d9cf", "#f1bd72", "#95b5ff", "#ef9cba", "#b2d784",
          "#c5a4f3", "#ff9c79", "#86d0ee", "#dfd88b", "#bbcad6",
          "#40bda6", "#d99847", "#628eea", "#dc729b", "#91b660",
          "#a784d7", "#e07d60", "#57aece", "#bcb465", "#889faf"]


def build_overview(context, facilities):
    zone = ZoneInfo(LOCAL_TIMEZONE)
    end = timestamp(context["generated_at"])
    start = end - timedelta(days=7)
    entries = {entry["slug"]: entry for entry in context["facilities"]}
    short_names = {
        "arlington": "Arlington", "childrens": "Children's", "nea": "NEA Baptist",
        "anderson": "Anderson", "baptist-medical-center": "Mississippi Baptist",
    }
    figure = go.Figure()
    for index, facility in enumerate(facilities):
        x, y, labels = [], [], []
        previous = None
        for point in entries.get(facility["slug"], {}).get("history", []):
            at = timestamp(point[0])
            if not start <= at <= end:
                continue
            if previous is not None and (at - previous).total_seconds() > context["policy"]["gap_seconds"]:
                x.append(None)
                y.append(None)
                labels.append(None)
            # UTC positions retain the order of repeated local hours at DST.
            # Explicit labels and tooltips always show America/Chicago time.
            x.append(at.timestamp() * 1000)
            y.append(point[1])
            labels.append(at.astimezone(zone).strftime("%b %d, %Y %I:%M %p %Z"))
            previous = at
        name = short_names.get(facility["slug"], facility["display_name"].removeprefix("Baptist Memorial Hospital-"))
        figure.add_trace(go.Scatter(
            x=x, y=y, customdata=labels, name=name, uid=facility["slug"],
            mode="lines+markers", marker={"size": 2}, connectgaps=False,
            line={"color": COLORS[index % len(COLORS)], "width": 1.6,
                  "dash": "solid" if index < 10 else "dot"},
            hovertemplate=html.escape(facility["display_name"]) +
                          "<br>%{customdata}<br><b>%{y} min</b><extra></extra>",
        ))

    def time_axis(hours):
        left = end - timedelta(hours=hours)
        ticks = [left + (end - left) * index / 4 for index in range(5)]
        return {"xaxis.range": [left.timestamp() * 1000, end.timestamp() * 1000],
                "xaxis.tickvals": [at.timestamp() * 1000 for at in ticks],
                "xaxis.ticktext": [at.astimezone(zone).strftime("%b %d<br>%I:%M %p %Z") for at in ticks]}

    initial = time_axis(168)
    figure.update_layout(
        template="plotly_dark", autosize=True, hovermode="closest", showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 58, "r": 48, "t": 14, "b": 58},
        font={"family": "Inter, Arial, sans-serif", "size": 16, "color": "#9fb1bd"},
        hoverlabel={"bgcolor": "#13232e", "font": {"family": "Inter, Arial, sans-serif",
                                                        "size": 16, "color": "#f0f6fa"}},
        meta={"generated_at": context["generated_at"]},
        xaxis={"type": "linear", "fixedrange": True, "range": initial["xaxis.range"],
               "tickmode": "array", "tickvals": initial["xaxis.tickvals"],
               "ticktext": initial["xaxis.ticktext"], "showgrid": False, "zeroline": False},
        yaxis={"rangemode": "tozero", "fixedrange": True, "gridcolor": "#22313b",
               "zerolinecolor": "#3b4c58", "nticks": 6},
    )
    return figure
