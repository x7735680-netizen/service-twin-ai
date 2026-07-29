import json
import os
import time
from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.experience_simulator import run_experience_simulation


st.set_page_config(page_title="Service Twin AI v0.8 Sandbox", layout="wide")

APP_BUILD = "2026-07-29-checkbox-fix-01"

FEATURE_FLAGS = {
    "p1_viewport_switching": False,
    "p1_emotion_bubbles": False,
    "p1_advanced_filtering_step2": False,
}

STEP_LABELS = {
    1: "Tell idea",
    2: "See flow",
    3: "Set focus",
    4: "Run",
    5: "Results",
    6: "Adjust",
}

DEFAULT_IDEA = (
    "Try an entrance triage and waiting content setup for a 70 sqm Aihuishou recycling store. "
    "Visitors enter, scan to register device details, wait for inspection, discuss the price, "
    "confirm data wiping, then receive payment. The observed problem is inspection congestion, "
    "pricing wait, and users leaving when the process feels unclear."
)

DEFAULT_EVENTS = [
    {
        "name": "Arrive and identify need",
        "duration": "1-2 min",
        "description": "Visitor enters the store and explains whether they want an estimate, recycling, or consultation.",
        "resources": ["Entrance", "Reception staff"],
        "risk": "Medium",
        "uncertain": False,
        "high_impact": False,
        "suggested": False,
        "reason": "The entrance step is stable, but arrival bursts can still overload reception.",
    },
    {
        "name": "Scan and preliminary registration",
        "duration": "2-4 min",
        "description": "Visitor enters model, storage, condition, and basic device information.",
        "resources": ["Self-scan station", "Reception support"],
        "risk": "Medium",
        "uncertain": True,
        "high_impact": True,
        "suggested": False,
        "reason": "Registration time depends on device familiarity and whether staff need to help.",
    },
    {
        "name": "Wait for inspection",
        "duration": "0-15 min",
        "description": "Visitor waits for an available inspection station and technician.",
        "resources": ["Waiting area", "Inspection queue"],
        "risk": "High",
        "uncertain": False,
        "high_impact": True,
        "suggested": False,
        "reason": "This directly affects the observed congestion and churn problem.",
    },
    {
        "name": "Device inspection",
        "duration": "8-15 min",
        "description": "Inspection staff check device exterior, functions, and system-generated quote basis.",
        "resources": ["Inspection desk x2", "Inspection staff"],
        "risk": "Medium",
        "uncertain": True,
        "high_impact": True,
        "suggested": False,
        "reason": "Inspection time is estimated and should be verified with field measurement.",
    },
    {
        "name": "Pricing conversation",
        "duration": "3-8 min",
        "description": "Visitor reviews the quote, asks about deductions, compares expectations, and decides.",
        "resources": ["Pricing counter", "Transaction staff"],
        "risk": "High",
        "uncertain": False,
        "high_impact": True,
        "suggested": False,
        "reason": "The observed result includes pricing wait and unclear explanation.",
    },
    {
        "name": "Data wiping and privacy confirmation",
        "duration": "5-12 min",
        "description": "Visitor confirms data removal and waits for visible handling or proof.",
        "resources": ["Data wiping station", "Back-stage support"],
        "risk": "Medium",
        "uncertain": True,
        "high_impact": False,
        "suggested": False,
        "reason": "High-value device visitors may require stronger privacy proof.",
    },
    {
        "name": "Payment and exit",
        "duration": "2-4 min",
        "description": "Visitor signs, receives payment, and leaves the store.",
        "resources": ["Payment system", "Transaction counter"],
        "risk": "Low",
        "uncertain": False,
        "high_impact": False,
        "suggested": False,
        "reason": "This is usually not a queue driver once the decision is made.",
    },
]

DEFAULT_PARAMS = {
    "hours": 3.0,
    "arrival_rate_per_hour": 15.0,
    "check_stations": 2,
    "check_time_min": 12.0,
    "transaction_time_min": 6.0,
    "data_wipe_time_min": 8.0,
    "has_entry_triage": True,
    "has_waiting_content": True,
    "has_price_explanation": True,
    "has_data_security_visualization": True,
}

DEFAULT_SOURCES = {
    "hours": "Manual input",
    "arrival_rate_per_hour": "System estimate",
    "check_stations": "Manual input",
    "check_time_min": "System estimate",
    "transaction_time_min": "System estimate",
    "data_wipe_time_min": "System estimate",
}

SOURCE_CONFIDENCE = {
    "System historical data": "High",
    "From upload": "Medium-high",
    "Field measurement": "Medium-high",
    "Manual input": "Medium",
    "System estimate": "Medium-low",
    "Not filled": "Low",
}

RISK_SORT = {"High": 3, "Medium": 2, "Low": 1}
CONFIDENCE_CLASS = {
    "High": "high",
    "Medium-high": "medium-high",
    "Medium": "medium",
    "Medium-low": "medium-low",
    "Low": "low",
}

MAPPING_RESULTS = [
    {"field": "Arrival pace per hour", "value": "16 groups/hr", "confidence": "Medium-high", "source": "From upload", "status": "mapped"},
    {"field": "Inspection duration", "value": "11.5 min", "confidence": "Medium-high", "source": "From upload", "status": "mapped"},
    {"field": "Waiting area capacity", "value": "Not found in document — keeping system estimate", "confidence": "Medium-low", "source": "System estimate", "status": "unmapped"},
    {"field": "Check stations", "value": "Upload: 2 | Manual: 2", "confidence": "Medium-high", "source": "From upload", "status": "conflict"},
]

CAUSAL_CHAINS = [
    {
        "title": "Inspection queue becomes visible",
        "chain": [
            ("Arrival pace", "System fluctuation", "Normal fluctuation created a clustered arrival window."),
            ("Inspection duration", "System estimate — unverified", "Average inspection time stayed above the inquiry user's patience threshold."),
            ("Waiting area capacity", "Designer input", "Capacity absorbed some users but made the queue visually salient."),
            ("Observed outcome", "Confirmed", "Inquiry users started leaving before inspection."),
        ],
        "low_confidence": "Inspection duration",
    },
    {
        "title": "Pricing wait triggers comparison behavior",
        "chain": [
            ("Pricing conversation time", "Designer input", "One transaction point handled several decisions in sequence."),
            ("Decision caution", "Confirmed", "Comparison-minded visitors required stronger price explanation."),
            ("Quote explanation", "System estimate — unverified", "Explanation support was present but not measured in the field."),
            ("Observed outcome", "Confirmed", "Pricing delay increased churn after quote review."),
        ],
        "low_confidence": "Quote explanation",
    },
]


def init_state():
    visited_from_url = {
        int(value)
        for value in st.query_params.get("visited", "").split(",")
        if value.isdigit() and 1 <= int(value) <= len(STEP_LABELS)
    }
    defaults = {
        "screen": "home",
        "step": 1,
        "completed_steps": set(),
        "visited_steps": visited_from_url,
        "idea_name": "Aihuishou inspection congestion",
        "idea": DEFAULT_IDEA,
        "where": "70 sqm Aihuishou recycling store",
        "who": "Inquiry users, confirmed sellers, comparison-minded visitors, high-value device visitors, reception staff, inspection staff",
        "scene_tags": {},
        "scene_tag_edits": set(),
        "step1_editing_tag": None,
        "events": DEFAULT_EVENTS.copy(),
        "params": DEFAULT_PARAMS.copy(),
        "param_sources": DEFAULT_SOURCES.copy(),
        "focus_factors": {
            "This round's focus": ["Inspection duration", "Arrival pace", "Waiting area capacity"],
            "Keep current estimate": ["Pricing conversation time", "Data wiping time"],
            "Not sure yet": ["Group visit composition"],
        },
        "personas": [],
        "moment_sort": "Sort by risk (high to low)",
        "delete_moment_idx": None,
        "focus_factor_edit": {},
        "surge_events": [],
        "timeline_state": "idle",
        "timeline_progress": 0,
        "timeline_speed": "paused",
        "selected_key_moment": "Inspection queue begins forming",
        "arrival_pace": "Normal fluctuation",
        "run_history": [],
        "active_run_name": "Current",
        "last_confirmation": "",
        "selected_moment_id": "moment_0",
        "selected_persona_index": 0,
        "selected_result_moment": 0,
        "adjust_variable": "Inspection time",
        "persona_mix": [18, 17, 17, 16, 16, 16],
        "persona_included": [True, True, True, True, True, True],
        "persona_previous_mix": [18, 17, 17, 16, 16, 16],
        "persona_undo": None,
        "persona_balance_preview": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    st.session_state["visited_steps"].update(visited_from_url)


def confidence_for(source):
    return SOURCE_CONFIDENCE.get(source, "Medium-low")


def confidence_bar(confidence):
    widths = {"High": 100, "Medium-high": 80, "Medium": 60, "Medium-low": 40, "Low": 20}
    colors = {
        "High": "#2e806d",
        "Medium-high": "#3db797",
        "Medium": "#3b8cea",
        "Medium-low": "#f0c85a",
        "Low": "#8d9095",
    }
    width = widths.get(confidence, 40)
    color = colors.get(confidence, "#f0c85a")
    st.markdown(
        f"<div class='confidence-track'><div class='confidence-fill' style='width:{width}%;background:{color}'></div></div>",
        unsafe_allow_html=True,
    )


def confidence_bar_html(confidence):
    widths = {"High": 100, "Medium-high": 80, "Medium": 60, "Medium-low": 40, "Low": 20}
    colors = {
        "High": "#2e806d",
        "Medium-high": "#3db797",
        "Medium": "#3b8cea",
        "Medium-low": "#f0c85a",
        "Low": "#8d9095",
    }
    return (
        "<div class='confidence-track'>"
        f"<div class='confidence-fill' style='width:{widths.get(confidence, 40)}%;background:{colors.get(confidence, '#f0c85a')}'></div>"
        "</div>"
    )


def extract_document_content(uploaded_file) -> dict:
    import csv
    import io
    import re
    import zipfile

    name = uploaded_file.name.lower()
    extracted = {}

    if name.endswith(".csv"):
        content = uploaded_file.read().decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(content))
        headers = reader.fieldnames or []
        rows = list(reader)
        field_map = {
            "area": "store_area",
            "floor_area": "store_area",
            "staff": "staff_count",
            "employees": "staff_count",
            "opening": "opening_time",
            "closing": "closing_time",
            "visitors": "daily_visitors",
            "customers": "daily_visitors",
        }
        for header in headers:
            for keyword, field in field_map.items():
                if keyword in header.lower() and rows:
                    extracted[field] = rows[0].get(header, "")
        if not extracted:
            extracted["raw_columns"] = ", ".join(headers)

    elif name.endswith((".xlsx", ".xls")):
        try:
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(uploaded_file.read()), read_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if rows:
                headers = [str(c) for c in rows[0] if c]
                extracted["raw_columns"] = ", ".join(headers)
                if len(rows) > 1:
                    extracted["sample_data"] = str(rows[1])
        except Exception as exc:
            extracted["parse_error"] = str(exc)

    elif name.endswith(".pdf"):
        raw = uploaded_file.read()
        try:
            text = raw.decode("latin-1", errors="ignore")
            areas = re.findall(r"(\d+)\s*(?:sqm|m2|m²|平方)", text)
            if areas:
                extracted["store_area"] = areas[0] + " sqm"
            staff_nums = re.findall(r"(\d+)\s*(?:staff|员工|人员)", text)
            if staff_nums:
                extracted["staff_count"] = staff_nums[0]
        except Exception:
            extracted["note"] = "PDF parsed - manual review recommended"

    elif name.endswith((".png", ".jpg", ".jpeg")):
        extracted["note"] = "Image uploaded. Manual field entry recommended for image files."

    elif name.endswith(".docx"):
        try:
            raw = uploaded_file.read()
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                with archive.open("word/document.xml") as doc:
                    xml = doc.read().decode("utf-8", errors="ignore")
                    text = re.sub(r"<[^>]+>", " ", xml)
                    extracted["raw_text_preview"] = text[:300].strip()
        except Exception:
            extracted["note"] = "DOCX parsed - review content above"

    return extracted


def apply_extracted_field_to_scene(field_key: str, value: str):
    scene_tags = st.session_state.get("scene_tags", {})
    params = st.session_state.get("params", {})
    mapping = {
        "store_area": ("params", "store_area"),
        "staff_count": ("params", "staff_count"),
        "opening_time": ("params", "opening_time"),
        "closing_time": ("params", "closing_time"),
        "daily_visitors": ("params", "arrival_rate_per_hour"),
    }
    if field_key not in mapping:
        return
    target, key = mapping[field_key]
    if target == "params":
        params[key] = value
        st.session_state["params"] = params
        st.session_state["param_sources"][key] = "From upload"
    elif target == "scene_tags":
        scene_tags[key] = value
        st.session_state["scene_tags"] = scene_tags


def get_field_confidence(field_key: str, value) -> str:
    if not value or str(value).strip() == "":
        return "Low"
    if field_key in ["store_area", "staff_count"]:
        return "Medium-high"
    return "Medium"


def confidence_to_style(level: str):
    mapping = {
        "High": ("#2e806d", 100),
        "Medium-high": ("#3db797", 80),
        "Medium": ("#3b8cea", 60),
        "Medium-low": ("#f0c85a", 40),
        "Low": ("#8d9095", 20),
    }
    return mapping.get(level, ("#8d9095", 20))


def apply_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Manrope:wght@600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
        :root {
          --font-display:"Manrope","Noto Sans SC","PingFang SC",sans-serif;
          --font-ui:"Inter","Noto Sans SC","PingFang SC",sans-serif;
          --font-mono:"IBM Plex Mono","SFMono-Regular",monospace;
          --canvas:#ffffff; --surface:#ffffff; --surface-soft:#f6f6f3; --surface-raised:#fbfbf9;
          --ink:#171717; --ink-secondary:#5f6166; --ink-tertiary:#8d9095;
          --border-subtle:#e2e2de; --border-strong:#a7a7a1;
          --primary:#171717; --primary-hover:#2a2a2a; --primary-soft:#efefec; --focus-ring:#3b8cea;
          --accent-cyan:#98cfd5; --accent-teal:#61b6ad; --accent-green:#3db797; --accent-blue:#3b8cea; --accent-yellow:#f0c85a;
          --space:#3db797; --space-soft:#e4f2ec; --process:#3b8cea; --process-soft:#e8f1fb;
          --attention:#75610b; --attention-soft:#fff4c9; --critical:#171717; --critical-soft:#f1f1ee;
          --success:#2e806d; --success-soft:#e4f2ec;
          --radius-sm:8px; --radius-md:12px; --radius-lg:16px; --radius-xl:24px;
          --shadow-hover:0 8px 24px rgba(32,36,49,.07);
        }
        html, body, [class*="css"] { font-family:var(--font-ui); }
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stAppViewContainer"] > .main { background:var(--canvas); color:var(--ink); }
        [data-testid="stAppViewContainer"] > .main { max-width:none; margin:0; box-shadow:none; }
        .main .block-container, .block-container {
          padding-top:132px !important; padding-bottom:96px !important;
          max-width:1280px !important; padding-left:40px !important; padding-right:40px !important;
        }
        header[data-testid="stHeader"] {
          display:block !important;
          height:0 !important;
          min-height:0 !important;
          background:transparent !important;
          pointer-events:none !important;
          overflow:visible !important;
          z-index:1000 !important;
        }
        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="stExpandSidebarButton"] {
          display:flex !important;
          visibility:visible !important;
          opacity:1 !important;
          position:fixed !important;
          top:118px !important;
          left:12px !important;
          z-index:1001 !important;
          pointer-events:auto !important;
        }
        [data-testid="collapsedControl"] button,
        [data-testid="stSidebarCollapsedControl"] button,
        [data-testid="stExpandSidebarButton"],
        [data-testid="stExpandSidebarButton"] button {
          display:inline-flex !important;
          visibility:visible !important;
          opacity:1 !important;
          background:var(--surface) !important;
          color:var(--ink) !important;
          border:1px solid var(--border-subtle) !important;
          border-radius:10px !important;
          box-shadow:0 2px 8px rgba(23,23,23,.14) !important;
        }
        [data-testid="stSidebarCollapseButton"] {
          visibility:visible !important;
          opacity:1 !important;
        }
        [data-testid="stSidebarCollapseButton"] button {
          color:var(--ink) !important;
        }
        h1, h2, h3 { font-family:var(--font-display); letter-spacing:0; color:var(--ink); }
        h1 { font-size:36px !important; line-height:1.2 !important; margin-bottom:8px !important; }
        h2 { font-size:26px !important; line-height:1.3 !important; }
        h3 { font-size:20px !important; line-height:1.4 !important; }
        p, label, [data-testid="stCaptionContainer"] { color:var(--ink-secondary); line-height:1.55; }
        [data-testid="stSidebar"] { background:var(--surface-soft); border-right:1px solid var(--border-subtle); }
        [data-testid="stSidebar"] .block-container { padding-top:20px !important; }
        [data-testid="stToolbar"] {
          display:flex !important; height:0 !important; min-height:0 !important;
          overflow:visible !important; pointer-events:none !important;
        }
        [data-testid="stToolbar"] > div { height:0 !important; min-height:0 !important; overflow:visible !important; }
        [data-testid="stDeployButton"], [data-testid="stMainMenu"], [data-testid="stDecoration"], [data-testid="stStatusWidget"] { display:none !important; }
        [data-testid="stExpandSidebarButton"] { pointer-events:auto !important; }
        div.stButton > button {
          border-radius:var(--radius-md); min-height:44px; border:1px solid var(--border-strong);
          background:var(--surface); color:var(--ink); font-weight:650; transition:all 120ms ease;
        }
        div.stButton > button:hover { border-color:var(--ink); box-shadow:var(--shadow-hover); }
        div.stButton > button:focus-visible { outline:3px solid var(--focus-ring); outline-offset:2px; }
        div.stButton > button[kind="primary"] {
          background:var(--surface); border-color:var(--border-strong); color:var(--ink);
        }
        div.stButton > button[kind="primary"]:hover {
          background:var(--surface-raised); border-color:var(--ink); color:var(--ink);
        }
        [class*="st-key-workflow_primary_"] button,
        [class*="st-key-workflow_primary_"] button p {
          background:var(--ink) !important; border-color:var(--ink) !important; color:#ffffff !important;
        }
        [class*="st-key-workflow_primary_"] button {
          min-height:52px !important; padding-left:22px !important; padding-right:22px !important;
          border-radius:12px !important; font-weight:600 !important;
        }
        [class*="st-key-workflow_primary_"] button:hover,
        [class*="st-key-workflow_primary_"] button:hover p {
          background:var(--primary-hover) !important; border-color:var(--primary-hover) !important; color:#ffffff !important;
        }
        [class*="st-key-workflow_primary_"] button:active,
        [class*="st-key-workflow_primary_"] button:active p {
          background:#000000 !important; border-color:#000000 !important; color:#ffffff !important;
        }
        [class*="st-key-workflow_primary_"] button:focus-visible {
          outline:3px solid rgba(23,23,23,.25) !important; outline-offset:3px !important;
        }
        [class*="st-key-workflow_primary_"] button:disabled,
        [class*="st-key-workflow_primary_"] button:disabled p {
          background:var(--ink) !important; border-color:var(--ink) !important; color:#ffffff !important;
          opacity:.52 !important; cursor:not-allowed !important;
        }
        [class*="st-key-workflow_primary_"] button:disabled p { opacity:1 !important; }
        div.stButton > button:disabled, div.stButton > button[kind="primary"]:disabled {
          background:#e2e2de !important; color:#3f4145 !important; border-color:#d2d2cd !important;
          box-shadow:none !important; opacity:1 !important; cursor:not-allowed !important;
        }
        [class*="st-key-workflow_primary_"] button:disabled,
        [class*="st-key-workflow_primary_"] button:disabled p {
          background:var(--ink) !important; border-color:var(--ink) !important; color:#ffffff !important;
          opacity:.52 !important; cursor:not-allowed !important;
        }
        [data-testid="stSidebar"] [class*="st-key-workflow_nav_"] button {
          width:100% !important; min-height:54px !important; border-radius:14px !important;
          background:#ffffff !important; border-color:#b8b8b2 !important; color:#555861 !important;
          box-shadow:none !important; opacity:1 !important;
        }
        [data-testid="stSidebar"] [class*="st-key-workflow_nav_"] button p {
          color:#555861 !important;
        }
        [data-testid="stSidebar"] [class*="st-key-workflow_nav_"] button[kind="primary"] {
          background:var(--ink) !important; border-color:var(--ink) !important; color:#ffffff !important;
        }
        [data-testid="stSidebar"] [class*="st-key-workflow_nav_"] button[kind="primary"] p {
          color:#ffffff !important;
        }
        [data-testid="stSidebar"] [class*="st-key-workflow_nav_"] button:disabled {
          background:#eeeeeb !important; border-color:#deded9 !important; color:#92949a !important;
          cursor:not-allowed !important;
        }
        [data-testid="stSidebar"] [class*="st-key-workflow_nav_"] button:disabled p {
          color:#92949a !important;
        }
        [data-baseweb="input"] > div, [data-baseweb="textarea"] > div, [data-baseweb="select"] > div {
          border-radius:10px !important; border-color:var(--border-subtle) !important; background:var(--surface-soft) !important;
        }
        [data-baseweb="input"] > div:focus-within, [data-baseweb="textarea"] > div:focus-within,
        [data-baseweb="select"] > div:focus-within { box-shadow:0 0 0 2px var(--focus-ring) !important; border-color:var(--ink) !important; }
        [data-testid="stSlider"] [role="slider"] {
          background:var(--ink) !important; border-color:var(--ink) !important; color:var(--ink) !important;
        }
        [data-testid="stSlider"] [data-testid="stSliderThumbValue"] {
          color:var(--ink) !important; border-color:var(--ink) !important;
        }
        [data-testid="stSlider"] [role="slider"]:focus-visible {
          outline:3px solid var(--focus-ring) !important; outline-offset:3px !important;
        }
        [data-testid="stToggle"] input:checked + div,
        [data-testid="stToggle"] [data-baseweb="checkbox"] input:checked + div {
          background-color:var(--ink) !important; border-color:var(--ink) !important;
        }
        [data-testid="stRadio"] [data-baseweb="radio"],
        [data-testid="stRadio"] [data-baseweb="radio"]:hover,
        [data-testid="stRadio"] [data-baseweb="radio"]:active,
        [data-testid="stRadio"] [data-baseweb="radio"]:focus-within,
        [data-testid="stRadio"] [data-baseweb="radio"]:has(input:checked) {
          background:#ffffff !important;
          color:#5f6169 !important;
          box-shadow:none !important;
          filter:none !important;
        }
        [data-testid="stRadio"] [data-baseweb="radio"] {
          display:inline-flex !important;
          align-items:center !important;
          gap:12px !important;
          line-height:1.2 !important;
        }
        [data-testid="stRadio"] [data-baseweb="radio"] > input {
          position:absolute !important;
          width:1px !important;
          height:1px !important;
          margin:-1px !important;
          padding:0 !important;
          overflow:hidden !important;
          clip:rect(0, 0, 0, 0) !important;
          white-space:nowrap !important;
          border:0 !important;
        }
        [data-testid="stRadio"] [data-baseweb="radio"] > :first-child {
          position:relative !important;
          width:22px !important;
          height:22px !important;
          min-width:22px !important;
          min-height:22px !important;
          flex:0 0 22px !important;
          box-sizing:border-box !important;
          border:2px solid #a8a8a8 !important;
          border-radius:50% !important;
          background:#ffffff !important;
          box-shadow:none !important;
          filter:none !important;
          margin:0 !important;
          padding:0 !important;
          overflow:visible !important;
          transform:none !important;
        }
        [data-testid="stRadio"] [data-baseweb="radio"] > :first-child > div {
          display:none !important;
        }
        [data-testid="stRadio"] [data-baseweb="radio"]:has(input:checked) > :first-child {
          border-color:var(--ink) !important;
          background:var(--ink) !important;
        }
        [data-testid="stRadio"] [data-baseweb="radio"]:has(input:checked) > :first-child::after {
          content:"" !important;
          position:absolute !important;
          left:50% !important;
          top:50% !important;
          width:8px !important;
          height:8px !important;
          border-radius:50% !important;
          background:#ffffff !important;
          transform:translate(-50%,-50%) !important;
          pointer-events:none !important;
        }
        [data-testid="stRadio"] [data-baseweb="radio"] > input + div,
        [data-testid="stRadio"] [data-baseweb="radio"]:has(input:checked) > input + div,
        [data-testid="stRadio"] [data-baseweb="radio"] > input + div p,
        [data-testid="stRadio"] [data-baseweb="radio"]:has(input:checked) > input + div p {
          background:transparent !important;
          color:#5f6169 !important;
          box-shadow:none !important;
          filter:none !important;
          margin:0 !important;
          padding:0 !important;
          line-height:1.2 !important;
        }
        [data-testid="stRadio"] [data-baseweb="radio"]:has(input:focus-visible) > :first-child {
          outline:2px solid var(--ink) !important; outline-offset:3px !important;
        }
        [data-testid="stToggle"] input:focus-visible + div {
          outline:3px solid var(--focus-ring) !important; outline-offset:2px !important;
        }
        [data-testid="stExpander"] { border:1px solid var(--border-subtle); border-radius:var(--radius-md); background:var(--surface); }
        [data-testid="stFileUploaderDropzone"] { border-color:var(--border-strong); border-radius:var(--radius-md); background:var(--surface-soft); }
        .app-header {
          position:fixed; top:0; left:0; right:0; z-index:997; height:56px; background:var(--surface);
          border-bottom:1px solid var(--border-subtle); display:flex; align-items:center; justify-content:space-between;
          padding:0 32px; font-size:13px;
        }
        .app-brand { display:flex; align-items:center; gap:12px; }
        .app-brand strong { font-family:var(--font-display); font-size:17px; color:var(--ink); }
        .project-name { color:var(--ink-tertiary); border-left:1px solid var(--border-subtle); padding-left:12px; }
        .app-meta { display:flex; align-items:center; gap:16px; color:var(--ink-secondary); }
        .save-dot { width:7px; height:7px; border-radius:50%; background:var(--success); display:inline-block; margin-right:6px; }
        .page-intro { margin:12px 0 32px; max-width:760px; }
        .page-kicker { color:var(--primary); font-size:13px; font-weight:700; margin-bottom:8px; }
        .page-intro h1 { margin:0 0 10px; }
        .page-intro p { font-size:18px; margin:0; color:var(--ink-secondary); }
        .section-card, .sandbox-card {
          background:var(--surface); border:1px solid var(--border-subtle); border-radius:var(--radius-lg);
          padding:24px; margin-bottom:20px; box-shadow:none;
        }
        .section-card h3, .sandbox-card h3 { margin-top:0; }
        .section-label { font-size:13px; font-weight:700; color:var(--primary); margin-bottom:6px; }
        .status-callout { display:flex; gap:12px; align-items:flex-start; background:var(--primary-soft); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:16px 18px; margin:12px 0 24px; }
        .status-callout.attention { background:var(--attention-soft); border-color:#d9c269; }
        .status-callout.success { background:var(--success-soft); border-color:#aed8ca; }
        .status-icon { width:28px; height:28px; border-radius:50%; display:flex; align-items:center; justify-content:center; background:var(--surface); color:var(--primary); font-weight:700; flex:0 0 auto; }
        .status-callout b { color:var(--ink); }
        .source-badge, .badge { display:inline-flex; align-items:center; border-radius:999px; padding:4px 9px; font-size:12px; font-weight:650; background:var(--surface-soft); color:var(--ink-secondary); border:1px solid var(--border-subtle); margin-right:6px; }
        .source-badge.system { background:var(--attention-soft); color:var(--attention); border-color:#d9c269; }
        .source-badge.designer { background:var(--process-soft); color:#245f9f; border-color:#b5d1ed; }
        .source-badge.confirmed { background:var(--success-soft); color:var(--success); border-color:#aed8ca; }
        .sandbox-card { min-height:140px; }
        .entry-grid { display:grid; grid-template-columns:1.45fr .8fr .8fr; gap:18px; align-items:stretch; }
        .entry-grid .sandbox-card:first-child { background:var(--ink); color:white; border-color:var(--ink); }
        .entry-grid .sandbox-card:first-child h3, .entry-grid .sandbox-card:first-child p { color:white; }
        .st-key-home_entry_grid [data-testid="stHorizontalBlock"] { align-items:stretch; gap:18px; }
        .st-key-home_entry_grid [data-testid="stColumn"] {
          display:flex; align-items:stretch; align-self:stretch; min-width:0;
        }
        .st-key-home_entry_grid [data-testid="stColumn"] > [data-testid="stVerticalBlock"],
        .st-key-home_entry_grid [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] {
          width:100%; height:100%; display:flex; align-items:stretch;
        }
        .st-key-home_primary_card,
        .st-key-home_template_card,
        .st-key-home_continue_card {
          width:100%; height:100%; min-height:236px; display:flex; flex-direction:column; flex:1 1 auto;
          box-sizing:border-box;
          padding:24px; border:1px solid var(--border-subtle); border-radius:var(--radius-lg);
          background:var(--surface);
        }
        .st-key-home_primary_card > [data-testid="stVerticalBlock"],
        .st-key-home_template_card > [data-testid="stVerticalBlock"],
        .st-key-home_continue_card > [data-testid="stVerticalBlock"] {
          width:100%; height:100%; display:flex; flex-direction:column;
        }
        .st-key-home_primary_card {
          background:var(--ink); border-color:var(--ink);
        }
        .st-key-home_primary_card h3,
        .st-key-home_primary_card p,
        .st-key-home_primary_card .section-label { color:#ffffff !important; }
        .st-key-home_primary_card [data-testid="stElementContainer"]:has(.stButton),
        .st-key-home_template_card [data-testid="stElementContainer"]:has(.stButton),
        .st-key-home_continue_card [data-testid="stElementContainer"]:has(.stButton) { margin-top:auto; padding-top:28px; }
        .st-key-home_primary_card div.stButton > button {
          background:#ffffff !important; border-color:#ffffff !important; color:var(--ink) !important;
        }
        .st-key-home_primary_card div.stButton > button p { color:var(--ink) !important; }
        .st-key-home_primary_card div.stButton > button:hover {
          background:var(--surface-raised) !important; border-color:var(--surface-raised) !important; color:var(--ink) !important;
        }
        .st-key-home_template_card div.stButton > button,
        .st-key-home_continue_card div.stButton > button {
          background:#ffffff !important; border-color:var(--border-subtle) !important; color:var(--ink) !important;
        }
        .session-row { display:grid; grid-template-columns:1fr auto; gap:12px; align-items:center; background:var(--surface); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:14px 16px; margin-bottom:10px; }
        .chip-row { display:flex; gap:8px; flex-wrap:wrap; margin:.35rem 0 1rem; }
        .chip { display:inline-flex; align-items:center; gap:6px; min-height:32px; border-radius:999px; padding:5px 11px; font-size:13px; border:1px solid var(--border-subtle); background:var(--surface); color:var(--ink-secondary); }
        .chip.confirmed { background:var(--success-soft); border-color:#aed8ca; color:var(--success); }
        .chip.pending { background:var(--attention-soft); border-color:#d9c269; color:var(--attention); }
        .chip.missing { color:var(--ink-tertiary); background:var(--surface-soft); border-style:dashed; }
        [class*="st-key-understanding_tile_"] {
          display:flex; flex-direction:column; min-height:220px; padding:22px 24px;
          background:#ffffff; border:1px solid #e4e2dc; border-radius:18px;
          box-sizing:border-box; margin-bottom:12px; transition:border-color 120ms ease, box-shadow 120ms ease;
        }
        [class*="st-key-understanding_tile_"]:has(input:not([type="hidden"])),
        [class*="st-key-understanding_tile_"]:has(textarea) {
          border-color:#202431; box-shadow:0 0 0 2px rgba(32,36,49,.08);
        }
        [class*="st-key-understanding_tile_"] > [data-testid="stVerticalBlock"] {
          min-height:174px; display:flex; flex-direction:column; gap:12px;
        }
        .understanding-tile-label {
          color:#7b808c; font-size:14px; font-weight:700; line-height:1.2; text-transform:uppercase;
        }
        [class*="st-key-edit_understanding_"] { flex:1 1 auto; display:flex; }
        [class*="st-key-edit_understanding_"] div.stButton { width:100%; display:flex; }
        [class*="st-key-edit_understanding_"] button {
          width:100% !important; min-height:86px !important; height:auto !important; padding:0 !important;
          justify-content:flex-start !important; align-items:flex-start !important; text-align:left !important;
          border:0 !important; border-radius:0 !important; background:transparent !important;
          color:#202431 !important; box-shadow:none !important; cursor:text !important;
        }
        [class*="st-key-edit_understanding_"] button p {
          color:#202431 !important; font-size:17px !important; font-weight:500 !important;
          line-height:1.5 !important; text-align:left !important; white-space:normal !important;
        }
        [class*="st-key-edit_understanding_"] button:hover,
        [class*="st-key-edit_understanding_"] button:focus-visible {
          background:#fbfbf9 !important; box-shadow:none !important;
        }
        [class*="st-key-understanding_tile_"] [data-baseweb="input"] > div,
        [class*="st-key-understanding_tile_"] [data-baseweb="textarea"] > div {
          background:#fcfcfa !important; border-color:#d9d7d0 !important; border-radius:12px !important;
        }
        [class*="st-key-understanding_tile_"] textarea { min-height:110px !important; resize:vertical !important; }
        [class*="st-key-save_understanding_"] button {
          background:var(--ink) !important; border-color:var(--ink) !important; color:#ffffff !important;
        }
        [class*="st-key-save_understanding_"] button p { color:#ffffff !important; }
        [class*="st-key-cancel_understanding_"] button {
          background:#ffffff !important; border-color:var(--border-subtle) !important; color:var(--ink) !important;
        }
        [class*="st-key-understanding_tile_"] .chip { align-self:flex-start; margin-top:auto; }
        .mapping-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }
        .mapping-card { background:var(--surface); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:16px; min-height:150px; }
        .mapping-card.conflict { border-color:#d2ad51; background:var(--attention-soft); }
        [class*="st-key-moment_detail_card_"] {
          width:100%; background:#ffffff; border:1px solid #e4e2dc;
          border-radius:20px; padding:28px 32px; margin-bottom:18px;
          box-shadow:0 2px 10px rgba(32,36,49,.035); box-sizing:border-box;
        }
        [class*="st-key-moment_detail_card_"] > [data-testid="stVerticalBlock"] {
          gap:0;
        }
        .moment-detail-header { padding-bottom:24px; border-bottom:1px solid #ece9e2; }
        .moment-eyebrow {
          color:#5f6572; font-size:14px; font-weight:700; line-height:1.2; margin-bottom:8px;
        }
        .moment-detail-title {
          color:#202431; font-family:var(--font-display); font-size:28px; line-height:1.25;
          font-weight:700; margin:0 0 16px;
        }
        .moment-status-row { display:flex; flex-wrap:wrap; gap:10px; }
        .moment-status-chip {
          display:inline-flex; align-items:center; min-height:30px; padding:4px 10px;
          border:1px solid var(--border-subtle); border-radius:999px; background:#f7f7f4;
          color:#5f6572; font-size:12px; font-weight:650;
        }
        .moment-status-chip.reviewed { background:var(--success-soft); border-color:#aed8ca; color:var(--success); }
        .moment-status-chip.pending { background:var(--attention-soft); border-color:#d9c269; color:var(--attention); }
        .moment-status-chip.risk-low { background:#f3f4f2; border-color:#d8d9d5; color:#62666d; }
        .moment-status-chip.risk-medium { background:#f7f1de; border-color:#e2c978; color:#7b5b11; }
        .moment-status-chip.risk-high { background:#f1f1ee; border-color:#a8a8a2; color:#202431; }
        .moment-section-heading {
          color:#5f6572; font-size:14px; font-weight:700; line-height:1.2; margin:24px 0 12px;
        }
        .moment-section-divider { height:1px; background:#ece9e2; margin:24px 0 0; }
        [class*="st-key-moment_detail_card_"] [data-baseweb="input"] > div,
        [class*="st-key-moment_detail_card_"] [data-baseweb="textarea"] > div,
        [class*="st-key-moment_detail_card_"] [data-baseweb="select"] > div {
          background:#fbfbf9 !important;
        }
        [class*="st-key-moment_detail_card_"] textarea { min-height:120px !important; resize:vertical !important; }
        [class*="st-key-moment_settings_"] {
          padding:16px 18px; border:1px solid #ece9e2; border-radius:12px; background:#fbfbf9;
        }
        [class*="st-key-moment_settings_"] > [data-testid="stVerticalBlock"] { gap:14px; }
        [class*="st-key-step2_uncertain_"],
        [class*="st-key-step2_impact_"],
        [class*="st-key-step2_keep_"],
        [class*="st-key-step2_uncertain_"] [data-testid="stCheckbox"],
        [class*="st-key-step2_impact_"] [data-testid="stCheckbox"],
        [class*="st-key-step2_keep_"] [data-testid="stCheckbox"],
        [class*="st-key-step2_uncertain_"] label,
        [class*="st-key-step2_impact_"] label,
        [class*="st-key-step2_keep_"] label,
        [class*="st-key-step2_uncertain_"] label > div,
        [class*="st-key-step2_impact_"] label > div,
        [class*="st-key-step2_keep_"] label > div,
        [class*="st-key-step2_uncertain_"] label p,
        [class*="st-key-step2_impact_"] label p,
        [class*="st-key-step2_keep_"] label p {
          background:transparent !important;
          color:#202431 !important;
        }
        [class*="st-key-step2_uncertain_"] label,
        [class*="st-key-step2_impact_"] label,
        [class*="st-key-step2_keep_"] label {
          display:inline-flex !important;
          align-items:center !important;
          gap:12px !important;
        }
        [class*="st-key-moment_actions_"] { margin-top:20px; padding-top:20px; border-top:1px solid #ece9e2; }
        [class*="st-key-moment_actions_"] [data-testid="stExpander"] { background:#fbfbf9; }
        .badge.high { background:var(--critical-soft); color:var(--critical); }
        .badge.info { background:var(--process-soft); color:var(--process); }
        .badge.warn { background:var(--attention-soft); color:#79520a; }
        .moment-actions { display:flex; gap:8px; flex-wrap:wrap; padding-top:12px; border-top:1px solid var(--border-subtle); margin-top:12px; }
        .delete-confirm { background:var(--critical-soft); border:1px solid var(--border-strong); border-radius:var(--radius-md); padding:12px; margin-top:8px; }
        .factor-zone { background:var(--surface); border:1px solid var(--border-subtle); border-radius:var(--radius-lg); padding:16px; min-height:168px; }
        .factor-zone.focus-zone { background:var(--primary-soft); border:2px solid var(--ink); }
        .factor-zone.keep-zone { background:var(--process-soft); }
        .factor-zone.unsure-zone { background:var(--attention-soft); }
        .factor-item { border:1px solid var(--border-subtle); background:var(--surface); border-radius:var(--radius-md); padding:10px; margin:8px 0; }
        .persona-card { position:relative; background:var(--surface); border:1px solid var(--border-subtle); border-radius:var(--radius-lg); padding:20px; min-height:176px; overflow:hidden; }
        .persona-card.selected { border:2px solid var(--ink); padding:19px; }
        .persona-card::before { content:""; position:absolute; top:0; left:0; right:0; height:4px; background:var(--persona-color,var(--primary)); }
        .persona-name { font-family:var(--font-display); font-weight:700; color:var(--ink); font-size:17px; margin-bottom:6px; }
        .persona-story { min-height:44px; font-size:14px; color:var(--ink-secondary); }
        .persona-meta { display:grid; grid-template-columns:1fr 1fr; gap:8px 14px; margin-top:12px; padding-top:12px; border-top:1px solid var(--border-subtle); }
        .persona-meta-item { font-size:12px; color:var(--ink-secondary); }
        .persona-meta-item b { display:block; color:var(--ink); font-size:12px; margin-bottom:2px; }
        .dot-row { display:flex; gap:7px; align-items:center; margin:8px 0; }
        .dot-select { width:14px; height:14px; border-radius:50%; border:2px solid #8391a4; display:inline-block; }
        .dot-select.active { background:var(--primary); border-color:var(--primary); }
        .confidence-track { height:7px; background:#e8e6e0; border-radius:999px; overflow:hidden; margin:6px 0 10px; }
        .confidence-fill { height:100%; border-radius:999px; }
        .metric-strip { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }
        .metric-card { background:var(--surface); border:1px solid var(--border-subtle); border-radius:var(--radius-lg); padding:18px; }
        .metric-card h3 { font-size:28px !important; margin:8px 0; }
        .notice { border:1px solid var(--border-subtle); background:var(--primary-soft); border-radius:var(--radius-md); padding:12px 14px; color:var(--ink); }
        .event-log { background:var(--surface); color:var(--ink); border:1px solid var(--border-subtle); border-radius:var(--radius-lg); padding:16px; min-height:220px; font-size:13px; line-height:1.8; }
        .log-queue { color:var(--attention); }.log-churn { color:var(--ink); font-weight:700; }.log-resolution { color:var(--success); }.log-staff { color:var(--process); }
        .canvas-wrap { border:1px solid #3c4253; border-radius:var(--radius-lg); overflow:hidden; background:#151725; }
        .causal-chain { background:var(--surface); border:1px solid var(--border-subtle); border-radius:var(--radius-lg); padding:16px; }
        .causal-item { display:grid; grid-template-columns:1fr auto; gap:10px; align-items:center; padding:10px 0; border-bottom:1px solid var(--border-subtle); }
        .causal-arrow { color:var(--ink-tertiary); padding-left:14px; }
        .source-label { border-radius:999px; padding:3px 8px; font-size:12px; font-weight:650; }
        .source-gray { background:var(--surface-soft); color:var(--ink-secondary); }
        .source-blue { background:var(--process-soft); color:#245f9f; }
        .source-yellow { background:var(--attention-soft); color:var(--attention); }
        .source-green { background:var(--success-soft); color:var(--success); }
        .delta-row { display:flex; gap:14px; flex-wrap:wrap; background:var(--surface); border:1px solid var(--border-subtle); border-radius:var(--radius-lg); padding:16px; margin-top:12px; }
        .delta-good { color:var(--success); font-weight:700; }
        .delta-flat { color:var(--ink-secondary); font-weight:700; }
        .timeline-track { height:10px; background:#e3e0da; border-radius:999px; overflow:hidden; margin:8px 0; }
        .timeline-fill { height:100%; background:var(--primary); }
        .surge-card { background:var(--surface); border:1px solid var(--border-subtle); border-radius:var(--radius-lg); padding:16px; min-height:260px; }
        .timeline-marker { display:inline-block; border-radius:999px; background:var(--attention-soft); border:1px solid #d5b965; color:var(--attention); padding:4px 8px; margin:3px; font-size:12px; }
        .persona-quick-controls { margin:0 0 20px; padding:12px 14px; border:1px solid var(--border-subtle); border-top:0; border-radius:0 0 var(--radius-lg) var(--radius-lg); background:var(--surface); }
        .persona-lens { font-size:12px; color:var(--ink-tertiary); margin-bottom:8px; }
        .mix-summary { display:flex; justify-content:space-between; align-items:center; gap:16px; background:var(--surface-soft); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:14px 16px; margin:18px 0; }
        .st-key-persona_confirm_bar {
          position:sticky; bottom:0; z-index:90; background:rgba(255,255,255,.97);
          border-top:1px solid var(--border-subtle); padding:12px 0; margin-top:24px;
          backdrop-filter:blur(10px);
        }
        .st-key-persona_confirm_bar div.stButton { display:flex; justify-content:flex-start; }
        .st-key-persona_confirm_bar button { min-width:260px; min-height:48px; padding-left:24px; padding-right:24px; }
        .sidebar-stage { padding:4px 0 16px; }
        .sidebar-stage .step-index { color:var(--primary); font-size:12px; font-weight:700; text-transform:uppercase; }
        .sidebar-stage h2 { font-size:22px !important; margin:6px 0; }
        .sidebar-summary { background:var(--surface-soft); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:14px; margin:12px 0 16px; }
        .sidebar-persona-editor { border-top:1px solid var(--border-subtle); margin-top:20px; padding-top:18px; }
        .sidebar-nav-label { font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:var(--ink-tertiary); font-weight:700; margin:18px 0 8px; }
        @media (max-width: 1024px) {
          .main .block-container, .block-container { padding-left:24px !important; padding-right:24px !important; }
          .entry-grid, .metric-strip, .mapping-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
        }
        @media (max-width: 767px) {
          .main .block-container, .block-container { padding-top:126px !important; padding-left:16px !important; padding-right:16px !important; }
          .app-header { padding:0 16px; }
          .project-name, .app-meta .help-label { display:none; }
          .entry-grid, .metric-strip, .mapping-grid, .understanding-grid { grid-template-columns:1fr; }
          h1 { font-size:30px !important; }
        }
        @media (prefers-reduced-motion: reduce) {
          *, *::before, *::after { animation-duration:.01ms !important; transition-duration:.01ms !important; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def confirm(message, step=None):
    st.session_state["last_confirmation"] = message
    st.session_state["confirmation_seen_at"] = str(date.today())
    if step:
        st.session_state["completed_steps"].add(step)


def mark_step_visited(step):
    visited = st.session_state.setdefault("visited_steps", set())
    if step not in visited:
        visited.add(step)
    visited_value = ",".join(str(item) for item in sorted(visited))
    if st.query_params.get("visited") != visited_value:
        st.query_params["visited"] = visited_value


def generate_scene_tags():
    where = st.session_state.get("where") or "Aihuishou recycling store"
    who = st.session_state.get("who") or "Visitors and store staff"
    idea = st.session_state.get("idea") or DEFAULT_IDEA
    return {
        "Location": where,
        "Visitors": "Inquiry users, confirmed sellers, comparison-minded visitors, high-value device visitors",
        "Service staff": "Reception staff, inspection staff, transaction staff, data wiping support",
        "Main spaces": "Entrance, Waiting area, Inspection area, Pricing area, Data wiping, Exit",
        "Tried change": "Entrance triage, waiting content, quote explanation, data wiping visualization",
        "Observed result": "Inspection congestion, pricing wait, unclear process, user churn",
        "Idea summary": idea[:120],
    }


def generate_personas():
    return [
        {
            "name": "Evidence Seeker",
            "lens": "Evidence-led lens",
            "narrative": "Looks for facts and proof before committing.",
            "color": "#d9dde5",
            "dimension": "Known information level",
            "traits": ["Information need", "Question frequency"],
            "dot_value": 3,
            "numeric_label": "Inquiry frequency",
            "numeric_value": 4,
            "numeric_min": 1,
            "numeric_max": 10,
            "numeric_suffix": "times per visit",
            "trigger_conditions": ["Missing inspection evidence", "Unclear quote breakdown"],
            "source": "System estimate",
        },
        {
            "name": "Feeling-led Visitor",
            "lens": "Feeling-led lens",
            "narrative": "Trust and emotion shape how long the wait feels.",
            "color": "#98cfd5",
            "dimension": "Emotional baseline",
            "traits": ["Wait patience", "Starting trust"],
            "wait_patience": 12,
            "dot_label": "Trust start point",
            "dot_value": 3,
            "trigger_conditions": ["No acknowledgement while waiting", "Abrupt price explanation"],
            "source": "System estimate",
        },
        {
            "name": "Risk Checker",
            "lens": "Risk-checking lens",
            "narrative": "Looks for downside, price gaps, and reasons to leave.",
            "color": "#343434",
            "dimension": "Decision caution",
            "traits": ["Risk sensitivity", "Exit threshold"],
            "dot_label": "Price comparison tendency",
            "dot_value": 4,
            "trigger": "20% below",
            "trigger_conditions": ["Quote falls below expectation", "Privacy process is unclear"],
            "source": "System estimate",
        },
        {
            "name": "Value Optimist",
            "lens": "Value-seeking lens",
            "narrative": "Stays engaged when the service makes value visible.",
            "color": "#f0c85a",
            "dimension": "Expected value perception",
            "traits": ["Value expectation", "Satisfaction baseline"],
            "dot_label": "Satisfaction baseline",
            "dot_value": 3,
            "tags": ["fast payout", "transparent quote", "bonus offer"],
            "trigger_conditions": ["Visible benefit", "Transparent quote"],
            "source": "System estimate",
        },
        {
            "name": "Explorer",
            "lens": "Exploration lens",
            "narrative": "Is open to a new path when the conditions feel clear.",
            "color": "#61b6ad",
            "dimension": "New process acceptance",
            "traits": ["Change openness", "Trial conditions"],
            "dot_label": "Willingness to try proposed change",
            "dot_value": 3,
            "tags": ["shorter wait", "staff explains first", "privacy proof"],
            "trigger_conditions": ["A faster route is offered", "The next step is explained"],
            "source": "System estimate",
        },
        {
            "name": "Control Planner",
            "lens": "Planning lens",
            "narrative": "Needs structure, timing, and a visible next step.",
            "color": "#3b8cea",
            "dimension": "Control need",
            "traits": ["Control need", "Opacity tolerance"],
            "dot_label": "Opacity tolerance",
            "dot_value": 2,
            "inquiry_after": 8,
            "trigger_conditions": ["Wait time is unknown", "Ownership of the next step is unclear"],
            "source": "System estimate",
        },
    ]


def ensure_persona_records():
    suggested = generate_personas()
    current = st.session_state.get("personas", [])
    if len(current) != len(suggested):
        st.session_state["personas"] = suggested
        return
    for index, defaults in enumerate(suggested):
        merged = {**defaults, **current[index]}
        merged["color"] = defaults["color"]
        merged.pop("hat", None)
        current[index] = merged
    st.session_state["personas"] = current


def reset_persona(index, regenerate=False):
    st.session_state["persona_undo"] = {
        "index": index,
        "persona": dict(st.session_state["personas"][index]),
    }
    persona = dict(generate_personas()[index])
    if regenerate:
        scene = st.session_state.get("idea_name") or "the current service idea"
        persona["narrative"] = f"Generated for {scene}: {persona['narrative']}"
    st.session_state["personas"][index] = persona
    for field in ["name", "narrative", "dimension", "triggers", "source", "level"]:
        st.session_state.pop(f"persona_{field}_{index}", None)
        st.session_state.pop(f"sidebar_persona_{field}_{index}", None)


def undo_persona_change():
    undo = st.session_state.get("persona_undo")
    if not undo:
        return
    index = undo["index"]
    st.session_state["personas"][index] = undo["persona"]
    for field in ["name", "narrative", "dimension", "triggers", "source", "level"]:
        st.session_state.pop(f"sidebar_persona_{field}_{index}", None)
    st.session_state["persona_undo"] = None


def persona_balance_values():
    included = st.session_state["persona_included"]
    active = [index for index, enabled in enumerate(included) if enabled]
    if not active:
        return list(st.session_state["persona_mix"])
    base, remainder = divmod(100, len(active))
    return [base + (1 if index in active[:remainder] else 0) if index in active else 0 for index in range(len(included))]


def apply_persona_balance():
    values = st.session_state.get("persona_balance_preview") or persona_balance_values()
    for index, value in enumerate(values):
        st.session_state["persona_mix"][index] = value
        if value:
            st.session_state["persona_previous_mix"][index] = value
        st.session_state[f"persona_mix_input_{index}"] = value
        st.session_state[f"sidebar_persona_mix_{index}"] = value
    st.session_state["persona_balance_preview"] = None


def sync_persona_include(index, widget_key):
    included = bool(st.session_state[widget_key])
    previous = st.session_state["persona_included"][index]
    if included != previous:
        if included:
            value = max(1, int(st.session_state["persona_previous_mix"][index]))
        else:
            value = int(st.session_state["persona_mix"][index])
            if value > 0:
                st.session_state["persona_previous_mix"][index] = value
            value = 0
        st.session_state["persona_mix"][index] = value
        st.session_state[f"persona_mix_input_{index}"] = value
        st.session_state[f"sidebar_persona_mix_{index}"] = value
    st.session_state["persona_included"][index] = included
    st.session_state[f"persona_include_{index}"] = included
    st.session_state[f"sidebar_persona_include_{index}"] = included
    st.session_state["persona_balance_preview"] = None


def sync_persona_mix(index, widget_key):
    value = int(st.session_state[widget_key]) if st.session_state["persona_included"][index] else 0
    st.session_state["persona_mix"][index] = value
    if value > 0:
        st.session_state["persona_previous_mix"][index] = value
    st.session_state[f"persona_mix_input_{index}"] = value
    st.session_state[f"sidebar_persona_mix_{index}"] = value
    st.session_state["persona_balance_preview"] = None


def render_persona_editor():
    ensure_persona_records()
    index = min(max(int(st.session_state.get("selected_persona_index", 0)), 0), 5)
    persona = st.session_state["personas"][index]
    st.markdown("<div class='sidebar-persona-editor'>", unsafe_allow_html=True)
    st.markdown("<div class='sidebar-nav-label'>Persona editor</div>", unsafe_allow_html=True)
    st.markdown(f"### {persona['name']}")
    st.caption("Edits here update the selected card immediately.")

    persona["name"] = st.text_input(
        "Persona name",
        value=persona["name"],
        key=f"sidebar_persona_name_{index}",
    )
    persona["narrative"] = st.text_area(
        "Behaviour narrative",
        value=persona["narrative"],
        key=f"sidebar_persona_narrative_{index}",
    )
    persona["dimension"] = st.text_input(
        "Dominant behaviour parameter",
        value=persona["dimension"],
        key=f"sidebar_persona_dimension_{index}",
    )
    persona["dot_value"] = st.slider(
        "Dominant level",
        1,
        5,
        int(persona.get("dot_value", 3)),
        key=f"sidebar_persona_level_{index}",
    )
    persona["trigger_conditions"] = st.multiselect(
        "Trigger conditions",
        options=persona.get("trigger_conditions", []),
        default=persona.get("trigger_conditions", []),
        accept_new_options=True,
        key=f"sidebar_persona_triggers_{index}",
        help="Remove a token or type a new condition and press Enter.",
    )

    include_key = f"sidebar_persona_include_{index}"
    if include_key not in st.session_state:
        st.session_state[include_key] = st.session_state["persona_included"][index]
    st.checkbox(
        "Include in this run",
        key=include_key,
        on_change=sync_persona_include,
        args=(index, include_key),
    )
    mix_key = f"sidebar_persona_mix_{index}"
    if mix_key not in st.session_state:
        st.session_state[mix_key] = int(st.session_state["persona_mix"][index])
    st.number_input(
        "Simulated share (%)",
        min_value=0,
        max_value=100,
        step=1,
        key=mix_key,
        disabled=not st.session_state["persona_included"][index],
        on_change=sync_persona_mix,
        args=(index, mix_key),
    )
    persona["source"] = st.selectbox(
        "Source",
        list(SOURCE_CONFIDENCE.keys()),
        index=list(SOURCE_CONFIDENCE.keys()).index(persona.get("source", "System estimate")),
        key=f"sidebar_persona_source_{index}",
    )
    st.markdown(source_badge(persona["source"]), unsafe_allow_html=True)
    confidence_bar(confidence_for(persona["source"]))

    st.button(
        "Regenerate this persona",
        key=f"sidebar_persona_regenerate_{index}",
        on_click=reset_persona,
        args=(index, True),
        use_container_width=True,
    )
    st.button(
        "Reset to suggested values",
        key=f"sidebar_persona_reset_{index}",
        on_click=reset_persona,
        args=(index, False),
        use_container_width=True,
    )
    if st.session_state.get("persona_undo"):
        st.button("Undo last persona reset", on_click=undo_persona_change, use_container_width=True)
    st.caption("Saved just now")
    st.markdown("</div>", unsafe_allow_html=True)


def parse_list_tag(value):
    return [item.strip() for item in value.split(",") if item.strip()]


def visitor_types_from_tags():
    return parse_list_tag(st.session_state.get("scene_tags", {}).get("Visitors", "")) or ["Inquiry users", "Confirmed sellers"]


def staff_roles_from_tags():
    return parse_list_tag(st.session_state.get("scene_tags", {}).get("Service staff", "")) or ["Reception staff", "Inspection staff"]


def move_factor(zone_name, item, direction):
    zone_order = ["This round's focus", "Keep current estimate", "Not sure yet"]
    current_idx = zone_order.index(zone_name)
    target_idx = current_idx + direction
    if target_idx < 0 or target_idx >= len(zone_order):
        return
    zones = st.session_state["focus_factors"]
    if item in zones[zone_name]:
        zones[zone_name].remove(item)
        if len(zones[zone_order[target_idx]]) < 3 or zone_order[target_idx] != "This round's focus":
            zones[zone_order[target_idx]].append(item)
        else:
            zones[zone_name].append(item)


def remove_factor(zone_name, item):
    zones = st.session_state["focus_factors"]
    if item in zones[zone_name]:
        zones[zone_name].remove(item)


def add_factor(zone_name, item):
    clean = item.strip()
    if clean and clean not in st.session_state["focus_factors"][zone_name]:
        st.session_state["focus_factors"][zone_name].append(clean)


def _risk_key(risk):
    return str(risk or "low").strip().lower()


def _risk_label(risk):
    key = _risk_key(risk)
    return {"high": "High", "medium": "Medium", "low": "Low"}.get(key, "Low")


def _ensure_step2_event_ids(events):
    for i, ev in enumerate(events):
        if "id" not in ev:
            ev["id"] = f"moment_{i}"


def render_focus_factors_drag():
    factor_zones = st.session_state["focus_factors"]
    suggested = st.session_state.get(
        "suggested_factors",
        [
            "Inspection duration",
            "Arrival pace",
            "Waiting area capacity",
            "Staff response time",
            "Pricing communication",
        ],
    )
    assigned = (
        factor_zones.get("This round's focus", [])
        + factor_zones.get("Keep current estimate", [])
        + factor_zones.get("Not sure yet", [])
    )
    zones = {
        "source": [factor for factor in suggested if factor not in assigned],
        "focus": factor_zones.get("This round's focus", []),
        "keep": factor_zones.get("Keep current estimate", []),
        "unsure": factor_zones.get("Not sure yet", []),
    }
    all_factors_json = json.dumps(zones)
    drag_html = f"""
    <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;width:100%;font-family:Inter,Arial,sans-serif;">
      <div id="zone-source" class="drop-zone" data-bg="#ffffff" style="min-height:148px;padding:12px;background:#ffffff;border:1px dashed #b8b5ad;border-radius:12px;">
        <div style="font-size:12px;color:#5f6572;margin-bottom:8px;font-weight:700;">AVAILABLE FACTORS</div>
      </div>
      <div id="zone-focus" class="drop-zone" data-bg="#efefec" style="min-height:148px;padding:12px;background:#efefec;border:2px solid #171717;border-radius:12px;">
        <div style="font-size:12px;color:#171717;margin-bottom:8px;font-weight:700;">FOCUS THIS RUN</div>
      </div>
      <div id="zone-keep" class="drop-zone" data-bg="#e7eef9" style="min-height:148px;padding:12px;background:#e7eef9;border:1px dashed #7697ca;border-radius:12px;">
        <div style="font-size:12px;color:#365f9f;margin-bottom:8px;font-weight:700;">KEEP AS ESTIMATED</div>
      </div>
      <div id="zone-unsure" class="drop-zone" data-bg="#fff2cf" style="min-height:148px;padding:12px;background:#fff2cf;border:1px dashed #c79b38;border-radius:12px;">
        <div style="font-size:12px;color:#79520a;margin-bottom:8px;font-weight:700;">NOT SURE YET</div>
      </div>
    </div>
    <script>
    const initialZones = {all_factors_json};
    const zoneMap = {{'zone-source':'source','zone-focus':'focus','zone-keep':'keep','zone-unsure':'unsure'}};
    let currentZones = JSON.parse(JSON.stringify(initialZones));
    function publishZones() {{
      window.parent.postMessage({{type:'streamlit:setComponentValue', value:JSON.stringify(currentZones)}}, '*');
    }}
    function renderZones() {{
      Object.entries(zoneMap).forEach(([zoneId, zoneKey]) => {{
        const container = document.getElementById(zoneId);
        const header = container.querySelector('div');
        container.innerHTML = '';
        container.appendChild(header);
        (currentZones[zoneKey] || []).forEach((factor, idx) => {{
          const chip = document.createElement('div');
          chip.draggable = true;
          chip.dataset.zone = zoneKey;
          chip.dataset.index = idx;
          chip.style.cssText = `
            padding:7px 10px;margin:4px 2px;background:#ffffff;border:1px solid #e4e2dc;border-radius:9px;
            font-size:12px;color:#202431;cursor:grab;display:inline-block;box-shadow:0 2px 6px rgba(32,36,49,.04);`;
          chip.textContent = factor;
          chip.addEventListener('dragstart', e => {{
            e.dataTransfer.setData('text/plain', JSON.stringify({{zone:zoneKey,index:idx,factor}}));
            chip.style.opacity = '0.4';
          }});
          chip.addEventListener('dragend', () => chip.style.opacity = '1');
          container.appendChild(chip);
        }});
      }});
    }}
    document.querySelectorAll('.drop-zone').forEach(zone => {{
      zone.addEventListener('dragover', e => {{
        e.preventDefault();
        zone.style.boxShadow = '0 0 0 3px #3b8cea';
      }});
      zone.addEventListener('dragleave', () => zone.style.boxShadow = 'none');
      zone.addEventListener('drop', e => {{
        e.preventDefault();
        zone.style.boxShadow = 'none';
        const data = JSON.parse(e.dataTransfer.getData('text/plain'));
        const targetZone = zoneMap[zone.id];
        if (data.zone === targetZone) return;
        currentZones[data.zone].splice(data.index, 1);
        currentZones[targetZone].push(data.factor);
        publishZones();
        renderZones();
      }});
    }});
    renderZones();
    </script>
    """
    components.html(drag_html, height=230)
    with st.expander("Apply a factor arrangement", expanded=False):
        st.caption("The arrangement bridge is kept out of the main workspace so technical data is never shown as page content.")
        zone_result = st.text_input(
            "Factor arrangement data",
            value=json.dumps(zones),
            key="focus_zones_result",
            label_visibility="collapsed",
        )
        if st.button("Apply arrangement", key="confirm_zones"):
            try:
                new_zones = json.loads(zone_result)
                st.session_state["focus_factors"] = {
                    "This round's focus": new_zones.get("focus", []),
                    "Keep current estimate": new_zones.get("keep", []),
                    "Not sure yet": new_zones.get("unsure", []),
                }
                st.rerun()
            except json.JSONDecodeError:
                st.error("The arrangement could not be applied. Try moving the factors again.")


def render_focus_section():
    st.markdown("### Focus board")
    st.caption(
        "Move factors between the four zones. Keep no more than three in Focus this run so the result can explain them clearly."
    )
    render_focus_factors_drag()

    col1, col2 = st.columns([4, 1])
    with col1:
        new_factor = st.text_input(
            "Add a custom factor",
            placeholder="e.g. Queue visibility",
            key="new_custom_factor",
            label_visibility="collapsed",
        )
    with col2:
        if st.button("Add", key="add_custom_factor_btn"):
            if new_factor.strip():
                focus_list = st.session_state["focus_factors"].get("This round's focus", [])
                focus_list.append(new_factor.strip())
                st.session_state["focus_factors"]["This round's focus"] = focus_list
                st.rerun()

    render_status_callout(
        "Two behaviours may still be missing",
        "Group visits and staff multitasking can change visible queue pressure without changing transaction demand.",
        "attention",
    )


def add_surge_event(kind, details):
    st.session_state["surge_events"].append({"type": kind, **details})
    st.rerun()


def surge_label(event):
    if isinstance(event, str):
        return event
    if event["type"] == "Visitor surge":
        return f"Visitor surge {event['start']} {event['duration']}min {event['scale']} · {event['visitor']}"
    if event["type"] == "User type composition shift":
        return f"Composition shift {event['start']}-{event['end']} · {event['visitor']} {event['percentage']}%"
    if event["type"] == "Group visit":
        return f"Group visit {event['arrival']} · {event['groups']} groups x {event['size']} · joint {event['joint']}"
    return f"Staff reduction {event['start']} {event['duration']}min · {event['role']}"


def render_surge_event_picker():
    st.subheader("Surge event card picker")
    visitors = visitor_types_from_tags()
    staff_roles = staff_roles_from_tags()
    surge_cols = st.columns(4)
    with surge_cols[0]:
        st.markdown("<div class='surge-card'><b>Visitor surge</b></div>", unsafe_allow_html=True)
        start = st.text_input("Start time", "14:00", key="surge_start")
        duration = st.number_input("Duration/min", 5, 180, 30, key="surge_duration")
        scale = st.selectbox("Scale", ["x1.5", "x2", "x3"], key="surge_scale")
        visitor = st.selectbox("Visitor type", visitors, key="surge_visitor")
        if st.button("Add to simulation", key="add_visitor_surge"):
            add_surge_event("Visitor surge", {"start": start, "duration": duration, "scale": scale, "visitor": visitor})
    with surge_cols[1]:
        st.markdown("<div class='surge-card'><b>User type composition shift</b></div>", unsafe_allow_html=True)
        start = st.text_input("Start time", "15:00", key="shift_start")
        end = st.text_input("End time", "16:00", key="shift_end")
        visitor = st.selectbox("Affected visitor type", visitors, key="shift_visitor")
        pct = st.slider("New percentage", 0, 100, 45, key="shift_pct")
        if st.button("Add to simulation", key="add_shift"):
            add_surge_event("User type composition shift", {"start": start, "end": end, "visitor": visitor, "percentage": pct})
    with surge_cols[2]:
        st.markdown("<div class='surge-card'><b>Group visit</b></div>", unsafe_allow_html=True)
        arrival = st.text_input("Arrival time", "14:30", key="group_arrival")
        groups = st.number_input("Simultaneous groups", 1, 20, 3, key="group_count")
        size = st.number_input("Average group size", 1, 8, 2, key="group_size")
        joint = st.toggle("Joint decision", value=True, key="group_joint")
        if st.button("Add to simulation", key="add_group"):
            add_surge_event("Group visit", {"arrival": arrival, "groups": groups, "size": size, "joint": joint})
    with surge_cols[3]:
        st.markdown("<div class='surge-card'><b>Staff reduction</b></div>", unsafe_allow_html=True)
        start = st.text_input("Start time", "16:00", key="staff_start")
        duration = st.number_input("Duration/min", 5, 180, 45, key="staff_duration")
        role = st.selectbox("Affected staff role", staff_roles, key="staff_role")
        if st.button("Add to simulation", key="add_staff"):
            add_surge_event("Staff reduction", {"start": start, "duration": duration, "role": role})


def render_surge_markers():
    if not st.session_state["surge_events"]:
        return
    st.caption("Timeline markers")
    for idx, item in enumerate(st.session_state["surge_events"]):
        c1, c2 = st.columns([5, 1])
        c1.markdown(f"<span class='timeline-marker'>{surge_label(item)}</span>", unsafe_allow_html=True)
        if c2.button("Remove", key=f"remove_surge_{idx}"):
            st.session_state["surge_events"].pop(idx)
            st.rerun()


def render_progress():
    steps = [
        ("1", "Tell the idea"),
        ("2", "See the flow"),
        ("3", "Set focus"),
        ("4", "Run"),
        ("5", "See results"),
        ("6", "Adjust"),
    ]
    current_step = st.session_state.get("step", 1)
    on_home = st.session_state.get("screen", "home") == "home"

    items_html = ""
    for num, label in steps:
        step_num = int(num)
        if on_home:
            state_class = "active" if step_num == 1 else "waiting"
            dot = num
        elif step_num < current_step:
            state_class = "done"
            dot = "✓"
        elif step_num == current_step:
            state_class = "active"
            dot = num
        else:
            state_class = "waiting"
            dot = num

        items_html += f"""
        <div class="prog-item {state_class}">
            <span class="prog-dot">{dot}</span>
            <span class="prog-label">{label}</span>
        </div>
        """
        if step_num < len(steps):
            items_html += '<div class="prog-line"></div>'

    st.markdown(
        f"""<div class="app-header">
<div class="app-brand"><strong>Service Twin AI</strong><span class="project-name">{st.session_state.get('idea_name', 'New service idea')}</span></div>
<div class="app-meta"><span><span class="save-dot"></span>Saved just now</span><span class="help-label">Help</span></div>
</div>
<div class="top-progress"><div class="prog-inner">{items_html}</div></div>
<style>
.top-progress {{
            position:fixed !important;
            top:56px !important;
            left:0 !important;
            right:0 !important;
            z-index:996 !important;
            width:100%;
            background:#ffffff;
            border-bottom:1px solid var(--border-subtle);
            height:52px;
            display:flex;
            align-items:center;
            justify-content:center;
        }}
.prog-inner {{
            display:flex;
            align-items:center;
            width:min(1120px,calc(100% - 64px));
        }}
.prog-item {{
            display:flex;
            align-items:center;
            justify-content:center;
            gap:8px;
            min-height:44px;
            padding:0 10px;
            font-size:13px;
            white-space:nowrap;
        }}
.prog-dot {{
            display:inline-flex; align-items:center; justify-content:center;
            width:24px; height:24px; border-radius:50%; font-size:11px; font-weight:700;
            background:var(--surface-soft); border:1px solid var(--border-subtle);
        }}
.prog-item.done {{ color:var(--success); }}
.prog-item.done .prog-dot {{ background:var(--success-soft); border-color:#b9dccf; }}
.prog-item.active {{
            color:var(--ink); font-weight:700; background:var(--primary-soft); border-radius:0;
            box-shadow:inset 0 -2px 0 var(--ink);
        }}
.prog-item.active .prog-dot {{ background:var(--ink); color:#fff; border-color:var(--ink); }}
.prog-item.waiting {{ color:var(--ink-tertiary); }}
.prog-line {{
            flex:1;
            min-width:16px;
            height:1px;
            background:var(--border-subtle);
        }}
@media (max-width:800px) {{
  .prog-inner {{ width:100%; overflow-x:auto; padding:0 10px; }}
  .prog-item {{ padding:0 8px; font-size:11px; }}
  .prog-line {{ min-width:12px; }}
}}
</style>
        """,
        unsafe_allow_html=True,
    )
    if st.session_state.get("last_confirmation"):
        st.markdown(f"<div class='notice'>{st.session_state['last_confirmation']}</div>", unsafe_allow_html=True)


def source_label_class(source):
    if source == "System fluctuation":
        return "source-gray"
    if source == "Designer input":
        return "source-blue"
    if source == "System estimate — unverified":
        return "source-yellow"
    if source == "Confirmed":
        return "source-green"
    return "source-gray"


def render_chain(chain):
    st.markdown("<div class='causal-chain'>", unsafe_allow_html=True)
    for idx, (var_name, source, explanation) in enumerate(chain):
        label = source
        if source == "System estimate — unverified":
            label = "System estimate - unverified"
        st.markdown(
            f"<div class='causal-item'><div><b>{var_name}</b><br><span>{explanation}</span></div>"
            f"<span class='source-label {source_label_class(source)}'>{label}</span></div>",
            unsafe_allow_html=True,
        )
        if idx < len(chain) - 1:
            st.markdown("<div class='causal-arrow'>↓</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def goto_step(step):
    mark_step_visited(step)
    st.session_state["screen"] = "workflow"
    st.session_state["step"] = step
    st.rerun()


def render_page_intro(step_label, title, copy):
    st.markdown(
        f"""
        <div class="page-intro">
          <div class="page-kicker">{step_label}</div>
          <h1>{title}</h1>
          <p>{copy}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_callout(title, copy, tone="default"):
    icon = {"attention": "!", "success": "✓"}.get(tone, "i")
    st.markdown(
        f"""
        <div class="status-callout {tone}">
          <div class="status-icon">{icon}</div>
          <div><b>{title}</b><br><span>{copy}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def source_badge(source):
    css_class = "system" if "System" in source else "designer"
    if source in ["Confirmed", "Field measurement", "From upload"]:
        css_class = "confirmed"
    return f'<span class="source-badge {css_class}">{source}</span>'


def persona_profile(persona, index):
    defaults = generate_personas()[index % 6]
    return (
        persona.get("name", defaults["name"]),
        persona.get("narrative", defaults["narrative"]),
        defaults["color"],
        persona.get("traits", defaults["traits"]),
    )


def render_home():
    render_page_intro(
        "Service design workspace",
        "Turn an early service idea into a day you can observe",
        "Describe a change, review how the service may unfold, and trace what shaped the simulated experience.",
    )
    with st.container(key="home_entry_grid"):
        c1, c2, c3 = st.columns([1.45, 0.8, 0.8])
        with c1:
            with st.container(key="home_primary_card"):
                st.markdown(
                    "<div class='section-label'>Start here</div><h3>Run a new idea</h3>"
                    "<p>Begin with the service change in your own words. The system will organise a first scene and show what needs your judgment.</p>",
                    unsafe_allow_html=True,
                )
                if st.button("Run a new idea", key="home_run_new", use_container_width=True):
                    st.session_state["screen"] = "workflow"
                    st.session_state["step"] = 1
                    st.session_state["simulation_done"] = False
                    st.rerun()
        with c2:
            with st.container(key="home_template_card"):
                st.markdown(
                    "<div class='section-label'>Faster start</div><h3>Start from a template</h3>"
                    "<p>Use a prepared retail service scene and adapt its people, spaces, and flow.</p>",
                    unsafe_allow_html=True,
                )
                if st.button("Start from a template", key="home_start_template", use_container_width=True):
                    st.session_state["idea_name"] = "Aihuishou inspection congestion"
                    st.session_state["idea"] = DEFAULT_IDEA
                    st.session_state["screen"] = "workflow"
                    st.session_state["step"] = 1
                    st.session_state["simulation_done"] = False
                    st.rerun()
        with c3:
            with st.container(key="home_continue_card"):
                st.markdown(
                    "<div class='section-label'>Pick up again</div><h3>Continue last session</h3>"
                    "<p>Return to the latest run with its assumptions, flow order, and outcomes intact.</p>",
                    unsafe_allow_html=True,
                )
                if st.button("Continue last session", key="home_continue_session", use_container_width=True):
                    st.session_state["show_history"] = True
    if st.session_state.get("show_history"):
        st.markdown("## Recent sessions")
        sessions = st.session_state.get("run_history") or [
            {"name": "Pre-fill during wait", "date": str(date.today()), "snapshot": "Inspection: 12 min | Staff: 2 | Churn: 54.5%"},
            {"name": "Added weekend peak", "date": str(date.today()), "snapshot": "Arrival: 24/hr | Staff: 2 | Churn: 38%"},
            {"name": "After considering group visits", "date": str(date.today()), "snapshot": "Groups: +4 | Pricing: 6 min | Churn: 42%"},
        ]
        for session in sessions:
            st.markdown(
                f"<div class='session-row'><div><b>{session['name']}</b><br><span>{session['date']} · {session['snapshot']}</span></div><div></div></div>",
                unsafe_allow_html=True,
            )
            if st.button("Quick resume", key=f"resume_{session['name']}"):
                st.session_state["screen"] = "workflow"
                st.session_state["step"] = 4 if st.session_state.get("experience_result") else 1
                st.rerun()


def render_understanding_tile(label, status, multiline=False):
    key_slug = label.lower().replace(" ", "_")
    editing = st.session_state.get("step1_editing_tag") == label
    value = st.session_state["scene_tags"].get(label, "")
    status_class = "pending" if status == "Needs detail" else "confirmed"

    with st.container(key=f"understanding_tile_{key_slug}"):
        st.markdown(f"<div class='understanding-tile-label'>{label}</div>", unsafe_allow_html=True)
        if editing:
            draft_key = f"understanding_draft_{key_slug}"
            if multiline:
                draft = st.text_area(
                    label,
                    value=value,
                    key=draft_key,
                    height=110,
                    label_visibility="collapsed",
                )
            else:
                draft = st.text_input(
                    label,
                    value=value,
                    key=draft_key,
                    label_visibility="collapsed",
                )
            save_col, cancel_col = st.columns(2)
            if save_col.button("Save", key=f"save_understanding_{key_slug}", use_container_width=True):
                st.session_state["scene_tags"][label] = draft.strip()
                st.session_state["scene_tag_edits"].add(label)
                st.session_state["step1_editing_tag"] = None
                st.session_state.pop(draft_key, None)
                st.rerun()
            if cancel_col.button("Cancel", key=f"cancel_understanding_{key_slug}", use_container_width=True):
                st.session_state["step1_editing_tag"] = None
                st.session_state.pop(draft_key, None)
                st.rerun()
        else:
            if st.button(
                value or "Click to add detail",
                key=f"edit_understanding_{key_slug}",
                use_container_width=True,
                help=f"Edit {label.lower()}",
            ):
                st.session_state["step1_editing_tag"] = label
                st.rerun()

        shown_status = "Edited" if label in st.session_state["scene_tag_edits"] else status
        shown_class = "confirmed" if shown_status == "Edited" else status_class
        st.markdown(f"<span class='chip {shown_class}'>{shown_status}</span>", unsafe_allow_html=True)


def render_step1():
    render_page_intro(
        "Step 1 · Tell the idea",
        "Describe the service change",
        "Start with the idea, not the form. The system will organise what it understands and show you what still needs your judgment.",
    )
    with st.container(border=True):
        st.markdown("<div class='section-label'>Your idea</div><h3>What do you want to try?</h3>", unsafe_allow_html=True)
        st.text_area(
            "What do you want to try?",
            key="idea",
            height=176,
            placeholder="Example: Add an entrance greeter and clearer waiting information to reduce uncertainty before inspection.",
            label_visibility="collapsed",
        )
        st.caption("Write naturally. You can refine people, spaces, and operating details after the system organises the scene.")

    st.markdown("### Optional context")
    c1, c2 = st.columns(2)
    with c1:
        st.text_input("Where does this happen? · Optional", key="where", placeholder="A store, app, clinic, or another service setting")
    with c2:
        st.text_input("Who is involved? · Optional", key="who", placeholder="Visitors, frontline staff, specialists, partners")
    generated_tags = generate_scene_tags()
    if not st.session_state["scene_tags"]:
        st.session_state["scene_tags"] = generated_tags
    else:
        for label, value in generated_tags.items():
            if label not in st.session_state["scene_tag_edits"]:
                st.session_state["scene_tags"][label] = value

    st.markdown("### What the system heard")
    tile_labels = ["Location", "Visitors", "Service staff", "Main spaces", "Tried change", "Observed result"]
    for row_start in range(0, len(tile_labels), 2):
        tile_columns = st.columns(2)
        for column, idx in zip(tile_columns, range(row_start, min(row_start + 2, len(tile_labels)))):
            label = tile_labels[idx]
            status = "Needs detail" if idx in [1, 3, 5] else "Suggested"
            with column:
                render_understanding_tile(label, status, multiline=label != "Location")

    st.markdown("### A few facts for the first run")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.session_state["params"]["hours"] = st.number_input("Service duration · hours", 0.5, 12.0, float(st.session_state["params"]["hours"]), 0.5)
        st.markdown(source_badge("Designer input"), unsafe_allow_html=True)
    with c2:
        st.number_input("Frontline staff", 1, 10, 1)
        st.markdown(source_badge("Designer input"), unsafe_allow_html=True)
    with c3:
        st.number_input("Specialist staff", 1, 10, 2)
        st.markdown(source_badge("System estimate"), unsafe_allow_html=True)
    st.text_input("Space zones", value=st.session_state["scene_tags"]["Main spaces"], key="step1_space_zones")
    with st.expander("Advanced settings", expanded=False):
        st.markdown("#### Upload project data")
        st.caption("Upload any existing research files. The system will extract relevant information and fill in scene details automatically.")
        uploaded_file = st.file_uploader(
            "Upload document",
            type=["xlsx", "csv", "pdf", "png", "jpg", "jpeg", "docx"],
            key="step1_doc_upload",
            label_visibility="collapsed",
        )

        if uploaded_file is not None:
            st.markdown(f"`{uploaded_file.name}` - {round(uploaded_file.size / 1024, 1)} KB")
            if st.button("Analyse document", key="analyse_doc_btn"):
                with st.spinner("Analysing document content..."):
                    st.session_state["doc_extracted"] = extract_document_content(uploaded_file)

            extracted = st.session_state.get("doc_extracted", {})
            if extracted:
                st.markdown("**Extracted information:**")
                st.caption("Review each field below. Accepted fields will be merged into your scene.")
                field_states = st.session_state.get("doc_field_states", {k: "pending" for k in extracted})
                for field_key, field_value in extracted.items():
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        edited_val = st.text_input(
                            field_key.replace("_", " ").title(),
                            value=str(field_value),
                            key=f"doc_field_{field_key}",
                        )
                        extracted[field_key] = edited_val
                    with col2:
                        confidence = get_field_confidence(field_key, field_value)
                        bar_color, bar_width = confidence_to_style(confidence)
                        st.markdown(
                            f"""
                            <div style="height:4px;width:{bar_width}%;background:{bar_color};border-radius:2px;margin-top:24px;"></div>
                            <div style="font-size:10px;color:#6b7280;margin-top:2px;">{confidence}</div>
                            """,
                            unsafe_allow_html=True,
                        )
                    with col3:
                        current_state = field_states.get(field_key, "pending")
                        if current_state == "pending":
                            if st.button("Accept", key=f"accept_{field_key}"):
                                field_states[field_key] = "accepted"
                                apply_extracted_field_to_scene(field_key, extracted[field_key])
                                st.session_state["doc_field_states"] = field_states
                                st.rerun()
                        elif current_state == "accepted":
                            st.markdown("<span style='color:#2e806d;font-size:12px;'>Added</span>", unsafe_allow_html=True)
                        if st.button("Reject", key=f"reject_{field_key}"):
                            field_states[field_key] = "rejected"
                            st.session_state["doc_field_states"] = field_states
                            st.rerun()

                if st.button("Accept all", key="accept_all_fields"):
                    for key in extracted:
                        apply_extracted_field_to_scene(key, extracted[key])
                        field_states[key] = "accepted"
                    st.session_state["doc_field_states"] = field_states
                    st.rerun()

        st.markdown("---")
        st.text_area("Manual field supplements", height=80)
    render_status_callout(
        "The scene is clear enough to map a first flow",
        "Three details still use system suggestions. You can change any assumption later.",
        "success",
    )
    if st.button("Use this scene and map the flow", type="primary", key="workflow_primary_scene"):
        confirm("The scene is clear enough to map a first flow. You can still change any assumption later.", 1)
        goto_step(2)


_COMPONENT_DIR = os.path.join(os.path.dirname(__file__), "components", "sortable_row")
_sortable_row = components.declare_component("sortable_row", path=_COMPONENT_DIR)


def _sortable_row_component(events: list):
    items_for_js = [
        {
            "id": ev.get("id", f"m_{i}"),
            "name": ev.get("name", "Unnamed"),
            "risk": _risk_key(ev.get("risk", "low")),
            "is_branch": bool(ev.get("is_branch", False)),
        }
        for i, ev in enumerate(events)
    ]
    return _sortable_row(
        items=json.dumps(items_for_js),
        key="sortable_row_main",
        default=None,
    )


def _render_thumbnail_row(events: list):
    result = _sortable_row_component(events)

    if result is not None:
        try:
            new_items = json.loads(result)
            id_to_ev = {ev["id"]: ev for ev in events}
            reordered = []

            for item in new_items:
                eid = item["id"]
                if eid in id_to_ev:
                    existing = dict(id_to_ev[eid])
                    existing["name"] = item.get("name", existing["name"])
                    existing["risk"] = _risk_label(item.get("risk", existing.get("risk", "low")))
                    existing["is_branch"] = bool(item.get("is_branch", existing.get("is_branch", False)))
                    reordered.append(existing)
                elif eid.startswith("new_"):
                    reordered.append(
                        {
                            "id": eid,
                            "name": item.get("name", "New moment"),
                            "duration": "",
                            "description": "",
                            "resources": [],
                            "risk": _risk_label(item.get("risk", "low")),
                            "uncertain": False,
                            "high_impact": False,
                            "suggested": False,
                            "reason": "",
                            "is_branch": False,
                        }
                    )
                elif eid.startswith("branch_"):
                    reordered.append(
                        {
                            "id": eid,
                            "name": item.get("name", "Branch"),
                            "duration": "",
                            "description": "",
                            "resources": [],
                            "risk": _risk_label(item.get("risk", "low")),
                            "uncertain": False,
                            "high_impact": False,
                            "suggested": False,
                            "reason": "",
                            "is_branch": True,
                        }
                    )

            current_signature = [
                (ev.get("id"), ev.get("name"), _risk_key(ev.get("risk", "low")), bool(ev.get("is_branch", False)))
                for ev in st.session_state.get("events", [])
            ]
            new_signature = [
                (ev.get("id"), ev.get("name"), _risk_key(ev.get("risk", "low")), bool(ev.get("is_branch", False)))
                for ev in reordered
            ]
            if new_signature != current_signature:
                st.session_state["events"] = reordered
                st.rerun()

        except Exception as ex:
            st.error(f"Sync error: {ex}")


def render_step2():
    render_page_intro(
        "Step 2 · See the flow",
        "Review how the service unfolds",
        "Move through the service moments in order. Review the nodes that are uncertain, influential, or different from how you understand the service.",
    )

    events = st.session_state.get("events", DEFAULT_EVENTS.copy())
    _ensure_step2_event_ids(events)
    st.session_state["events"] = events

    flagged = sum(1 for event in events if event.get("uncertain") or event.get("high_impact"))
    render_status_callout(
        "Flow ready for review",
        f"{len(events)} service moments were generated. {flagged} need your judgment before the first run.",
        "attention" if flagged else "success",
    )

    _render_thumbnail_row(events)

    st.markdown("### Moment review")
    st.caption("The sequence above controls the service order. Use the compact editors below to review details and semantic states.")

    if "step2_sort_mode" not in st.session_state:
        st.session_state["step2_sort_mode"] = "Custom order"

    sort_mode = st.radio(
        "Sort details by",
        options=["Custom order", "Risk (high to low)"],
        horizontal=True,
        key="step2_sort_mode",
        label_visibility="collapsed",
    )

    display_events = list(st.session_state["events"])
    if sort_mode == "Risk (high to low)":
        risk_order = {"high": 0, "medium": 1, "low": 2}
        display_events = sorted(display_events, key=lambda x: risk_order.get(_risk_key(x.get("risk", "low")), 2))

    for i, event in enumerate(display_events):
        _render_moment_detail_card(event, i)
        st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

    if st.button("Confirm the flow and choose a focus", type="primary", key="workflow_primary_flow"):
        flagged = sum(1 for event in st.session_state["events"] if event.get("uncertain") or event.get("high_impact"))
        confirm(f"The service flow is ready — {len(st.session_state['events'])} moments, with {flagged} carrying review context into the run.", 2)
        goto_step(3)


def _render_moment_detail_card(event, index):
    event_id = event.get("id", f"moment_{index}")
    risk_key = f"step2_risk_{event_id}"
    name_key = f"step2_name_{event_id}"
    duration_key = f"step2_duration_{event_id}"
    uncertain_key = f"step2_uncertain_{event_id}"
    risk = _risk_label(st.session_state.get(risk_key, event.get("risk", "low")))
    summary_name = st.session_state.get(name_key, event.get("name", "Service moment"))
    summary_duration = st.session_state.get(duration_key, event.get("duration", "")) or "Duration not set"
    summary_uncertain = bool(st.session_state.get(uncertain_key, event.get("uncertain", False)))
    resources = event.get("resources", [])
    if isinstance(resources, list):
        resources = " | ".join(resources)

    with st.container(key=f"moment_detail_card_{event_id}"):
        st.markdown(
            f"<div class='moment-detail-header'>"
            f"<div class='moment-eyebrow'>Moment {index + 1:02d}</div>"
            f"<div class='moment-detail-title'>{summary_name}</div>"
            f"<div class='moment-status-row'>"
            f"<span class='moment-status-chip'>{summary_duration}</span>"
            f"<span class='moment-status-chip {'pending' if summary_uncertain else 'reviewed'}'>"
            f"{'Needs review' if summary_uncertain else 'Reviewed'}</span>"
            f"<span class='moment-status-chip risk-{_risk_key(risk)}'>Risk: {risk}</span>"
            f"</div></div>",
            unsafe_allow_html=True,
        )

        st.markdown("<div class='moment-section-heading'>Basic details</div>", unsafe_allow_html=True)
        basic_row_one = st.columns([1.6, 0.7], gap="medium")
        with basic_row_one[0]:
            new_name = st.text_input("Moment name", event.get("name", ""), key=name_key)
        with basic_row_one[1]:
            new_risk = st.selectbox(
                "Risk",
                ["High", "Medium", "Low"],
                index=["High", "Medium", "Low"].index(risk),
                key=risk_key,
            )

        basic_row_two = st.columns([0.7, 1.6], gap="medium")
        with basic_row_two[0]:
            new_dur = st.text_input("Duration", event.get("duration", ""), key=duration_key)
        with basic_row_two[1]:
            resources_text = st.text_input("Resources", resources, key=f"step2_resources_{event_id}")

        st.markdown("<div class='moment-section-heading'>What happens in this moment?</div>", unsafe_allow_html=True)
        new_desc = st.text_area(
            "Moment description",
            event.get("description", ""),
            key=f"step2_desc_{event_id}",
            height=120,
            label_visibility="collapsed",
        )

        st.markdown("<div class='moment-section-divider'></div>", unsafe_allow_html=True)
        st.markdown("<div class='moment-section-heading'>Moment settings</div>", unsafe_allow_html=True)
        with st.container(key=f"moment_settings_{event_id}"):
            new_uncertain = st.checkbox(
                "This moment is uncertain",
                value=bool(event.get("uncertain")),
                key=uncertain_key,
            )
            new_high_impact = st.checkbox(
                "This moment may strongly affect the run",
                value=bool(event.get("high_impact")),
                key=f"step2_impact_{event_id}",
            )
            st.checkbox(
                "Keep the system's current understanding",
                value=True,
                key=f"step2_keep_{event_id}",
            )

        new_reason = event.get("reason", "")
        if new_uncertain:
            with st.expander("Uncertain reason"):
                new_reason = st.text_area("Reason", event.get("reason", ""), key=f"step2_reason_{event_id}", height=68)
        if new_high_impact:
            with st.expander("High impact reason"):
                st.write("Affects observed result: " + st.session_state["scene_tags"].get("Observed result", "waiting and churn"))

        with st.container(key=f"moment_actions_{event_id}"):
            with st.expander("Moment actions"):
                st.caption("Use removal only when this moment is not part of the service you want to simulate.")
                if st.button("Remove this moment", key=f"step2_remove_{event_id}"):
                    st.session_state["events"] = [item for item in st.session_state["events"] if item.get("id") != event_id]
                    st.rerun()

    evs = st.session_state.get("events", [])
    for j, ev in enumerate(evs):
        if ev.get("id") == event_id:
            evs[j] = {
                **ev,
                "name": new_name,
                "duration": new_dur,
                "description": new_desc,
                "resources": [part.strip() for part in resources_text.split("|") if part.strip()],
                "risk": _risk_label(new_risk),
                "uncertain": new_uncertain,
                "high_impact": new_high_impact,
                "reason": new_reason,
            }
            break
    st.session_state["events"] = evs


def render_factor_zone(zone_name, items):
    st.markdown(f"<div class='factor-zone'><b>{zone_name}</b>", unsafe_allow_html=True)
    zone_order = ["This round's focus", "Keep current estimate", "Not sure yet"]
    for idx, item in enumerate(list(items)):
        safe_key = f"{zone_name}_{idx}_{item}".replace(" ", "_").replace("'", "")
        st.markdown("<div class='factor-item'>", unsafe_allow_html=True)
        edited = st.text_input("Factor label", value=item, key=f"factor_edit_{safe_key}", label_visibility="collapsed")
        if edited != item and edited.strip():
            items[idx] = edited.strip()
            st.rerun()
        b1, b2, b3 = st.columns([1, 1, 1])
        with b1:
            if st.button("←", key=f"factor_left_{safe_key}", disabled=zone_order.index(zone_name) == 0):
                move_factor(zone_name, item, -1)
                st.rerun()
        with b2:
            if st.button("→", key=f"factor_right_{safe_key}", disabled=zone_order.index(zone_name) == len(zone_order) - 1):
                move_factor(zone_name, item, 1)
                st.rerun()
        with b3:
            if st.button("×", key=f"factor_remove_{safe_key}", help="Remove factor"):
                remove_factor(zone_name, item)
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_step3():
    render_page_intro(
        "Step 3 · Set focus",
        "Choose what to pay attention to",
        "Set the factors this run should explain first, then review the six visitor personas the system will simulate.",
    )
    render_focus_section()
    st.markdown("### Key inputs for this run")
    st.caption("Each input keeps its source and confidence visible so exploratory results are not mistaken for observed facts.")
    source_options = list(SOURCE_CONFIDENCE.keys())
    params = st.session_state["params"]
    sources = st.session_state["param_sources"]
    fields = [
        ("hours", "Operating hours", 0.5, 12.0, 0.5),
        ("arrival_rate_per_hour", "Arrival pace per hour", 1.0, 100.0, 1.0),
        ("check_stations", "Inspection stations", 1, 20, 1),
        ("check_time_min", "Inspection duration/min", 1.0, 60.0, 1.0),
        ("transaction_time_min", "Pricing conversation/min", 1.0, 60.0, 1.0),
        ("data_wipe_time_min", "Data wiping/min", 1.0, 60.0, 1.0),
    ]
    for row in range(0, len(fields), 3):
        cols = st.columns(3)
        for col, field in zip(cols, fields[row : row + 3]):
            key, label, low, high, step = field
            with col:
                if isinstance(params[key], int):
                    params[key] = st.number_input(label, int(low), int(high), int(params[key]), int(step))
                else:
                    params[key] = st.number_input(label, float(low), float(high), float(params[key]), float(step))
                sources[key] = st.selectbox(f"Source · {label}", source_options, index=source_options.index(sources.get(key, "System estimate")), key=f"source_{key}")
                confidence_bar(confidence_for(sources[key]))
    with st.expander("Advanced parameters"):
        st.subheader("Document upload")
        upload = st.file_uploader("Upload data document", type=["xlsx", "csv", "pdf", "png", "jpg", "jpeg"], key="step3_upload")
        if upload:
            st.subheader("Mapped fields")
            for row in range(0, len(MAPPING_RESULTS), 2):
                cols = st.columns(2)
                for col, item in zip(cols, MAPPING_RESULTS[row : row + 2]):
                    with col:
                        cls = "conflict" if item["status"] == "conflict" else ""
                        label = "Not found in document" if item["status"] == "unmapped" else item["source"]
                        st.markdown(
                            f"<div class='mapping-card {cls}'><b>{item['field']}</b><p>{item['value']}</p>"
                            f"<small>{label}</small>{confidence_bar_html(item['confidence'])}</div>",
                            unsafe_allow_html=True,
                        )
                        st.text_input("Edit mapped value", value=item["value"], key=f"mapped_value_{item['field']}", label_visibility="collapsed")
                        c1, c2 = st.columns(2)
                        c1.button("Accept", key=f"step3_accept_{item['field']}")
                        c2.button("Reject", key=f"step3_reject_{item['field']}")
            st.button("Accept all mappings", key="step3_accept_all")
        st.subheader("Full parameter table")
        adv_fields = [
            ("transaction_stations", "Pricing stations", 1, 10, 1, "System estimate"),
            ("data_wipe_stations", "Data wiping stations", 1, 10, 1, "System estimate"),
            ("simulation_runs", "Simulation runs", 10, 300, 10, "System historical data"),
            ("seed", "Random seed", 1, 99, 1, "Manual input"),
        ]
        for key, label, low, high, step, default_source in adv_fields:
            if key not in params:
                params[key] = low if key != "simulation_runs" else 100
                sources[key] = default_source
            params[key] = st.number_input(label, int(low), int(high), int(params[key]), int(step), key=f"adv_{key}")
            confidence_bar(confidence_for(sources.get(key, default_source)))
        st.text_area("Custom probability distribution")
        st.text_area("Technical sensitivity coefficients")
        st.caption("Model version: Service Twin sandbox v0.8")
    st.markdown("### Six visitor personas")
    ensure_persona_records()
    st.caption("Six distinct visitor profiles generated from the confirmed scene and flow. The mix is system-suggested until observed visitor data is added.")
    compare = st.toggle("Compare all six", key="persona_compare")
    if compare:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Persona": persona_profile(p, i)[0],
                        "Simulated share": f"{st.session_state['persona_mix'][i]}%",
                        "Primary lens": p.get("lens", p["dimension"]),
                        "Primary level": p.get("dot_value", "-"),
                        "Triggers": ", ".join(p.get("trigger_conditions", [])),
                        "Included": "Yes" if st.session_state["persona_included"][i] else "No",
                    }
                    for i, p in enumerate(st.session_state["personas"])
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    for row in range(0, len(st.session_state["personas"]), 2):
        cols = st.columns(2)
        for offset, (col, persona) in enumerate(zip(cols, st.session_state["personas"][row : row + 2])):
            persona_idx = row + offset
            profile_name, story, color, traits = persona_profile(persona, persona_idx)
            with col:
                selected_class = " selected" if st.session_state["selected_persona_index"] == persona_idx else ""
                st.markdown(
                    f"<div class='persona-card{selected_class}' style='--persona-color:{color}'>"
                    f"<div class='persona-lens'>{persona.get('lens', 'Visitor lens')}</div>"
                    f"<div class='persona-name'>{profile_name}</div><div class='persona-story'>{story}</div>"
                    f"<div class='persona-meta'>"
                    f"<div class='persona-meta-item'><b>Dominant parameter</b>{persona.get('dimension', traits[0])} · {persona.get('dot_value', 3)}/5</div>"
                    f"<div class='persona-meta-item'><b>Trigger conditions</b>{', '.join(persona.get('trigger_conditions', [])) or 'Not set'}</div>"
                    f"</div></div>",
                    unsafe_allow_html=True,
                )
                include_key = f"persona_include_{persona_idx}"
                if include_key not in st.session_state:
                    st.session_state[include_key] = st.session_state["persona_included"][persona_idx]
                st.checkbox(
                    "Include in this run",
                    key=include_key,
                    on_change=sync_persona_include,
                    args=(persona_idx, include_key),
                )
                mix_key = f"persona_mix_input_{persona_idx}"
                if mix_key not in st.session_state:
                    st.session_state[mix_key] = int(st.session_state["persona_mix"][persona_idx])
                st.number_input(
                    "Simulated share (%)",
                    min_value=0,
                    max_value=100,
                    step=1,
                    key=mix_key,
                    disabled=not st.session_state["persona_included"][persona_idx],
                    on_change=sync_persona_mix,
                    args=(persona_idx, mix_key),
                )
                if st.button("Edit persona", key=f"select_persona_{persona_idx}", use_container_width=True):
                    st.session_state["selected_persona_index"] = persona_idx
                    st.rerun()
    mix_total = sum(
        share for share, included in zip(st.session_state["persona_mix"], st.session_state["persona_included"]) if included
    )
    mix_state = "Ready to confirm" if mix_total == 100 else f"{100 - mix_total}% remaining" if mix_total < 100 else f"{mix_total - 100}% over"
    st.markdown(
        f"<div class='mix-summary'><b>Active mix total: {mix_total}%</b><span>{mix_state}</span></div>",
        unsafe_allow_html=True,
    )
    render_status_callout(
        "100% · Ready to confirm" if mix_total == 100 else "Persona shares must total 100%",
        f"Included personas currently total {mix_total}%. " + ("The run mix is complete." if mix_total == 100 else mix_state + "."),
        "success" if mix_total == 100 else "attention",
    )
    if mix_total != 100:
        if st.session_state.get("persona_balance_preview") is None:
            if st.button("Preview balanced shares", use_container_width=False):
                st.session_state["persona_balance_preview"] = persona_balance_values()
                st.rerun()
        else:
            preview = st.session_state["persona_balance_preview"]
            changes = [
                f"{st.session_state['personas'][i]['name']}: {st.session_state['persona_mix'][i]}% → {preview[i]}%"
                for i in range(6) if preview[i] != st.session_state["persona_mix"][i]
            ]
            st.markdown("**Balance preview**")
            st.caption(" · ".join(changes) if changes else "No changes are needed.")
            pc1, pc2 = st.columns(2)
            pc1.button("Apply balanced shares", on_click=apply_persona_balance, use_container_width=True)
            if pc2.button("Cancel", key="cancel_persona_balance", use_container_width=True):
                st.session_state["persona_balance_preview"] = None
                st.rerun()
        st.caption("Confirmation is unavailable until the included persona shares total exactly 100%.")
    with st.container(key="persona_confirm_bar"):
        if st.button(
            "Confirm focus and personas",
            type="primary",
            key="workflow_primary_focus",
            disabled=mix_total != 100,
            help="Persona shares must total 100%." if mix_total != 100 else None,
        ):
            confirm("Six visitor personas are ready for the exploratory run, with sources and review status preserved.", 3)
            goto_step(4)


def zones_from_tags():
    main_spaces = st.session_state.get("scene_tags", {}).get("Main spaces") or "Entrance, Waiting area, Inspection area, Pricing area, Exit"
    zones = [zone.strip() for zone in main_spaces.split(",") if zone.strip()]
    return zones[:8] or ["Entrance", "Waiting area", "Inspection area", "Pricing area", "Exit"]


def generate_canvas_html(config_json: str) -> str:
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0f0f1a; font-family:'Courier New',monospace; color:#e2e8f0; overflow:hidden; }}
#shell {{ display:flex; flex-direction:column; height:600px; width:100%; }}
#filter-bar {{ display:flex; align-items:center; padding:8px 12px; background:#13131f; border-bottom:1px solid #1e1e2e; gap:6px; flex-wrap:wrap; min-height:42px; flex-shrink:0; }}
.f-label {{ font-size:10px; color:#6b7280; margin-right:2px; }}
.f-btn {{ padding:3px 10px; border-radius:20px; border:1px solid #2a2a3a; background:transparent; color:#9ca3af; font-size:11px; cursor:pointer; transition:all .15s; display:flex; align-items:center; gap:4px; }}
.f-btn:hover {{ background:#1e1e2e; }}
.f-btn.active {{ color:#fff; background:#1e1e2e; border-color:#3a3a5a; }}
.f-dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; flex-shrink:0; }}
.f-sep {{ width:1px; height:16px; background:#1e1e2e; margin:0 4px; }}
#canvas-wrap {{ flex:1; position:relative; min-height:0; overflow:hidden; }}
canvas {{ display:block; width:100%; height:100%; image-rendering:pixelated; }}
#elog {{ position:absolute; right:8px; top:8px; width:210px; max-height:160px; overflow-y:auto; background:rgba(10,10,20,.88); border:1px solid #1e1e2e; border-radius:6px; padding:7px; font-size:10px; }}
.elog-head {{ color:#6b7280; font-size:9px; margin-bottom:4px; }}
.el {{ padding:2px 0; border-bottom:1px solid #13131f; color:#6b7280; }}
.el.q {{ color:#f0c85a; }} .el.c {{ color:#ffffff; font-weight:700; }} .el.r {{ color:#3db797; }} .el.s {{ color:#98cfd5; }}
#tl-section {{ background:#13131f; border-top:1px solid #1e1e2e; padding:10px 12px 8px; flex-shrink:0; }}
#tl-status {{ display:flex; justify-content:space-between; font-size:10px; color:#6b7280; margin-bottom:6px; }}
#tl-track {{ position:relative; height:28px; background:#0a0a14; border-radius:4px; margin-bottom:7px; cursor:pointer; overflow:visible; }}
#tl-fill {{ height:100%; background:linear-gradient(90deg,#98cfd5,#3b8cea); border-radius:4px; width:0%; pointer-events:none; transition:width .08s; }}
#tl-cursor {{ position:absolute; top:0; width:2px; height:100%; background:#fff; pointer-events:none; box-shadow:0 0 4px rgba(255,255,255,.4); }}
.km-marker {{ position:absolute; top:0; height:100%; width:2px; background:#f0c85a; cursor:pointer; z-index:10; }}
.km-label {{ position:absolute; top:-18px; left:50%; transform:translateX(-50%); white-space:nowrap; font-size:9px; color:#f0c85a; display:none; }}
.km-marker:hover .km-label {{ display:block; }}
#tl-controls {{ display:flex; align-items:center; gap:8px; }}
.tl-btn {{ padding:4px 10px; border-radius:4px; border:1px solid #2a2a3a; background:#1e1e2e; color:#cbd5e1; font-size:11px; cursor:pointer; }}
.tl-btn.active {{ background:#ffffff; color:#171717; border-color:#ffffff; }}
#surge-strip {{ flex:1; text-align:right; font-size:10px; color:#9ca3af; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }}
</style>
</head>
<body>
<div id="shell">
  <div id="filter-bar"></div>
  <div id="canvas-wrap">
    <canvas id="simCanvas"></canvas>
    <div id="elog"><div class="elog-head">EVENT LOG</div><div id="elog-items"></div></div>
  </div>
  <div id="tl-section">
    <div id="tl-status"><span id="time-label">09:00</span><span id="state-label">Paused · 1x</span></div>
    <div id="tl-track"><div id="tl-fill"></div><div id="tl-cursor"></div></div>
    <div id="tl-controls">
      <button class="tl-btn" data-action="pause">Pause</button>
      <button class="tl-btn active" data-action="normal">Normal speed</button>
      <button class="tl-btn" data-action="fast">4x speed</button>
      <span id="surge-strip"></span>
    </div>
  </div>
</div>
<script>
const config = {config_json};
const zones = config.zones && config.zones.length ? config.zones : ['Entrance','Waiting area','Inspection area','Pricing area','Exit'];
const visitors = [
  {{label:'All', color:'#cbd5e1'}},
  {{label:'Evidence Seeker', color:'#d9dde5', shape:0}},
  {{label:'Feeling-led Visitor', color:'#98cfd5', shape:1}},
  {{label:'Risk Checker', color:'#343434', shape:2}},
  {{label:'Value Optimist', color:'#f0c85a', shape:3}},
  {{label:'Explorer', color:'#61b6ad', shape:0}},
  {{label:'Control Planner', color:'#3b8cea', shape:1}}
];
const staff = [
  {{label:'Reception staff', color:'#61b6ad'}},
  {{label:'Specialist staff', color:'#3b6b72'}},
  {{label:'Transaction staff', color:'#7e7048'}}
];
const keyMoments = [
  {{label:'Group visit arrives', pct:30, time:'10:12'}},
  {{label:'Inspection queue begins forming', pct:45, time:'10:48'}},
  {{label:'Pricing wait spike', pct:68, time:'11:36'}}
];
const eventLog = [
  {{pct:8, cls:'s', text:'09:18  Reception staff switches to triage'}},
  {{pct:30, cls:'q', text:'10:12  Three groups arrive simultaneously'}},
  {{pct:45, cls:'q', text:'10:48  Inspection area queue begins forming'}},
  {{pct:58, cls:'s', text:'11:14  Reception staff handling two groups at once'}},
  {{pct:68, cls:'c', text:'11:36  Inquiry users begin leaving before inspection'}},
  {{pct:84, cls:'r', text:'12:10  Queue pressure eases after inspection desk clears'}}
];
let filter = 'All';
let running = false;
let speed = 1;
let progress = config.progress || 0;
let virtualT = 0;
const canvas = document.getElementById('simCanvas');
const ctx = canvas.getContext('2d');
const track = document.getElementById('tl-track');
const fill = document.getElementById('tl-fill');
const cursor = document.getElementById('tl-cursor');
const stateLabel = document.getElementById('state-label');
const timeLabel = document.getElementById('time-label');
const elogItems = document.getElementById('elog-items');
function fitCanvas() {{
  const r = canvas.parentElement.getBoundingClientRect();
  canvas.width = Math.max(640, Math.floor(r.width));
  canvas.height = Math.max(300, Math.floor(r.height));
}}
function renderFilters() {{
  const bar = document.getElementById('filter-bar');
  bar.innerHTML = '<span class="f-label">FILTER</span>';
  visitors.forEach(v => {{
    const btn = document.createElement('button');
    btn.className = 'f-btn' + (filter === v.label ? ' active' : '');
    btn.innerHTML = `<span class="f-dot" style="background:${{v.color}}"></span>${{v.label}}`;
    btn.onclick = () => {{ filter = v.label; renderFilters(); }};
    bar.appendChild(btn);
  }});
  const sep = document.createElement('span');
  sep.className = 'f-sep';
  bar.appendChild(sep);
  staff.forEach(s => {{
    const tag = document.createElement('span');
    tag.className = 'f-btn';
    tag.style.cursor = 'default';
    tag.innerHTML = `<span class="f-dot" style="background:${{s.color}}"></span>${{s.label}}`;
    bar.appendChild(tag);
  }});
}}
function zoneRects() {{
  const margin = 24;
  const cols = Math.ceil(Math.sqrt(zones.length));
  const rows = Math.ceil(zones.length / cols);
  const w = (canvas.width - margin * 2) / cols;
  const h = (canvas.height - margin * 2) / rows;
  return zones.map((name, i) => ({{
    name, x:margin + (i % cols) * w, y:margin + Math.floor(i / cols) * h,
    w:w - 12, h:h - 12
  }}));
}}
function drawSprite(x, y, color, state='walking', shape=0, isStaff=false) {{
  ctx.fillStyle = color;
  const bob = state === 'idle' ? Math.sin(virtualT / 220) * 1 : 0;
  y += bob;
  if (shape === 2) ctx.fillRect(x, y, 22, 14);
  else ctx.fillRect(x, y, 16, 16);
  ctx.fillStyle = isStaff ? '#111827' : '#f7d7b5';
  ctx.fillRect(x + 4, y - 8, 8, 8);
  ctx.fillStyle = '#111827';
  ctx.fillRect(x + 3, y + 16, 4, 8);
  ctx.fillRect(x + 10, y + 16, 4, 8);
  if (state === 'waiting') {{
    ctx.fillStyle = '#fff';
    ctx.fillRect(x + 13, y - 14, 12, 7);
    ctx.fillStyle = '#94a3b8';
    ctx.fillRect(x + 16, y - 11, 2, 2);
  }}
}}
function draw() {{
  fitCanvas();
  virtualT += running ? 12 * speed : 2;
  ctx.fillStyle = '#e8edf3';
  ctx.fillRect(0,0,canvas.width,canvas.height);
  const rects = zoneRects();
  rects.forEach((r, i) => {{
    const waitZone = r.name.toLowerCase().includes('waiting') || i === 1;
    const pressure = waitZone ? Math.min(.58, .12 + progress / 190 + (Math.sin(virtualT / 700) + 1) / 12) : .07;
    ctx.fillStyle = waitZone ? `rgba(240,200,90,${{pressure}})` : '#f9fafb';
    ctx.fillRect(r.x,r.y,r.w,r.h);
    ctx.strokeStyle = '#45515f';
    ctx.lineWidth = 2;
    ctx.strokeRect(r.x,r.y,r.w,r.h);
    ctx.fillStyle = '#1f2937';
    ctx.font = '600 14px Inter, Arial, sans-serif';
    ctx.fillText(r.name, r.x + 10, r.y + 22);
    ctx.fillStyle = progress > 65 && (waitZone || r.name.toLowerCase().includes('pricing')) ? '#171717' : progress > 40 && i % 2 ? '#f0c85a' : '#3db797';
    ctx.fillRect(r.x + r.w - 18, r.y + 10, 8, 8);
  }});
  for (let i=0; i<18; i++) {{
    const type = visitors[(i % (visitors.length - 1)) + 1];
    if (filter !== 'All' && filter !== type.label) continue;
    const route = rects[i % rects.length];
    const isQueue = route.name.toLowerCase().includes('waiting') || route.name.toLowerCase().includes('inspection');
    const x = isQueue ? route.x + 24 + (i % 5) * 24 : route.x + 18 + ((virtualT / 20 + i * 29) % Math.max(28, route.w - 54));
    const y = route.y + 58 + (isQueue ? Math.floor(i / 5) * 24 : (i % 3) * 30);
    drawSprite(x, y, type.color, isQueue ? 'waiting' : 'walking', type.shape, false);
  }}
  rects.forEach((r, i) => {{
    const s = staff[i % staff.length];
    drawSprite(r.x + r.w - 44, r.y + r.h - 45, s.color, i === 1 ? 'interacting' : 'idle', 0, true);
  }});
  if (running) progress = Math.min(100, progress + speed * .08);
  updateTimeline();
  requestAnimationFrame(draw);
}}
function updateTimeline() {{
  fill.style.width = progress + '%';
  cursor.style.left = `calc(${{progress}}% - 1px)`;
  const minutes = Math.round(progress / 100 * 240);
  const h = 9 + Math.floor(minutes / 60);
  const m = minutes % 60;
  timeLabel.textContent = String(h).padStart(2,'0') + ':' + String(m).padStart(2,'0');
  stateLabel.textContent = (running ? 'Running' : 'Paused') + ' · ' + speed + 'x';
  elogItems.innerHTML = eventLog.filter(e => e.pct <= progress + 1).map(e => `<div class="el ${{e.cls}}">${{e.text}}</div>`).join('');
}}
function renderMarkers() {{
  keyMoments.forEach(k => {{
    const mark = document.createElement('div');
    mark.className = 'km-marker';
    mark.style.left = k.pct + '%';
    mark.title = k.label;
    mark.innerHTML = `<span class="km-label">${{k.time}} ${{k.label}}</span>`;
    mark.onclick = e => {{ e.stopPropagation(); progress = k.pct; running = false; updateTimeline(); }};
    track.appendChild(mark);
  }});
}}
track.onclick = e => {{
  const r = track.getBoundingClientRect();
  progress = Math.max(0, Math.min(100, ((e.clientX - r.left) / r.width) * 100));
  running = false;
  updateTimeline();
}};
document.querySelectorAll('.tl-btn').forEach(btn => {{
  btn.onclick = () => {{
    document.querySelectorAll('.tl-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    if (btn.dataset.action === 'pause') running = false;
    if (btn.dataset.action === 'normal') {{ running = true; speed = 1; }}
    if (btn.dataset.action === 'fast') {{ running = true; speed = 4; }}
    updateTimeline();
  }};
}});
document.getElementById('surge-strip').textContent = (config.surgeEvents || []).length
  ? 'Scheduled events: ' + (config.surgeEvents || []).map(e => e.label || e.type).join(' · ')
  : 'No scenario events scheduled';
renderFilters();
renderMarkers();
updateTimeline();
requestAnimationFrame(draw);
</script>
</body>
</html>
"""


def render_step4_canvas():
    config = {
        "zones": zones_from_tags(),
        "surgeEvents": [{"type": item.get("type"), "label": surge_label(item)} for item in st.session_state.get("surge_events", [])],
        "progress": st.session_state.get("timeline_progress", 0),
    }
    components.html(generate_canvas_html(json.dumps(config)), height=600, scrolling=False)


def run_current_simulation(name="Current"):
    params = {k: v for k, v in st.session_state["params"].items() if k in {
        "hours",
        "arrival_rate_per_hour",
        "check_stations",
        "check_time_min",
        "transaction_stations",
        "transaction_time_min",
        "data_wipe_stations",
        "data_wipe_time_min",
        "has_entry_triage",
        "has_waiting_content",
        "has_price_explanation",
        "has_data_security_visualization",
        "simulation_runs",
        "seed",
    }}
    result = run_experience_simulation(**params)
    st.session_state["experience_result"] = result
    st.session_state["run_history"].append(
        {
            "name": name,
            "date": str(date.today()),
            "snapshot": f"Inspection: {params['check_time_min']} min | Staff: {params['check_stations']} | Churn: {result['summary']['dropoff_rate']*100:.1f}%",
            "result": result,
        }
    )
    return result


def render_step4():
    render_page_intro(
        "Step 4 · Run",
        "Run the service day",
        "Choose the arrival rhythm, add any disruption you want to test, and watch the six visitor personas, staff, and spaces respond over time.",
    )
    tabs = ["Current"] + [r["name"] for r in st.session_state["run_history"][-3:]]
    st.caption("Run history · " + "  /  ".join(tabs))
    setup_cols = st.columns([2, 1, 1])
    with setup_cols[0]:
        st.selectbox("Arrival rhythm", ["Relatively stable", "Normal fluctuation", "Clear peak period", "Highly unpredictable", "Custom"], key="arrival_pace")
    with setup_cols[1]:
        st.metric("Scenario events", len(st.session_state.get("surge_events", [])))
    with setup_cols[2]:
        st.metric("Run length", f"{st.session_state['params']['hours']:g} h")

    surge_events = st.session_state.get("surge_events", [])
    surge_expander_label = f"Scenario events ({len(surge_events)} scheduled)" if surge_events else "Add a disruption or change"
    with st.expander(surge_expander_label, expanded=False):
        render_surge_event_picker()
        render_surge_markers()

    st.markdown("### Spatial simulation view")
    render_step4_canvas()
    render_status_callout(
        "What is happening now" if st.session_state.get("simulation_done") else "Ready for an exploratory run",
        "The canvas keeps filters, people, zones, event markers, pause, speed, and key-moment controls in one simulation surface.",
        "success" if st.session_state.get("simulation_done") else "default",
    )

    sim_done = st.session_state.get("simulation_done", False)
    if not sim_done:
        if st.button("Start the simulation", key="workflow_primary_start_simulation", type="primary"):
            with st.spinner("Running simulation..."):
                run_current_simulation("Current")
                st.session_state["simulation_done"] = True
                st.session_state["timeline_progress"] = 100
                st.session_state["timeline_state"] = "complete"
                confirm("The run is complete — three moments are ready for closer review.", 4)
            st.rerun()
    else:
        if st.button("Review what happened", key="workflow_primary_review_results", type="primary"):
            if "experience_result" not in st.session_state:
                run_current_simulation("Current")
            confirm("The run is complete — three moments are ready for closer review.", 4)
            goto_step(5)


def notable_moments(result):
    top = result.get("summary", {}).get("main_dropoff_node", "waiting")
    return [
        ("Several groups arrive before the service has recovered", "09:10-09:25", ["Arrival rhythm", "Reception capacity", "Information need"], top),
        ("Waiting begins to spread from inspection into the waiting area", "10:05-10:32", ["Inspection duration", "Inspection stations", "Wait patience"], "Waiting area"),
        ("A longer pricing conversation gives risk-sensitive visitors time to reconsider", "11:15-11:35", ["Pricing conversation", "Risk sensitivity", "Quote explanation"], "Pricing area"),
    ]


def render_step5():
    render_page_intro(
        "Step 5 · See results",
        "What happened, and why",
        "Start with the moments that changed the experience. Select one to trace the assumptions, variables, and personas involved.",
    )
    if "experience_result" not in st.session_state:
        render_status_callout("No completed run yet", "Return to Run and start the simulation before reviewing results.", "attention")
        return
    result = st.session_state["experience_result"]
    render_status_callout(
        "The queue remained after the arrival burst passed",
        "Inspection demand recovered slowly. Feeling-led visitors and Risk Checkers were most likely to leave while the waiting area stayed visibly busy.",
        "default",
    )
    st.markdown("### Three moments worth a closer look")
    chains = CAUSAL_CHAINS + [
        {
            "title": "Arrival burst creates early ambiguity",
            "chain": [
                ("Visitor information level", "System fluctuation", "Several visitors arrived with incomplete device information."),
                ("Reception capacity", "Designer input", "One reception staff member handled the first questions."),
                ("Process opacity", "System estimate — unverified", "The model estimates uncertainty before registration."),
                ("Observed outcome", "Confirmed", "The entrance became a contributor to later queue pressure."),
            ],
            "low_confidence": "Process opacity",
        }
    ]
    for idx, (title, time_range, factors, space) in enumerate(notable_moments(result), start=1):
        with st.container(border=True):
            st.markdown(f"<div class='section-label'>{time_range} · {space}</div><h3>{title}</h3>", unsafe_allow_html=True)
            st.write("The experience changed as " + ", ".join(factors).lower() + " interacted in this part of the flow.")
            st.markdown("".join(f"<span class='chip'>{factor}</span>" for factor in factors), unsafe_allow_html=True)
            with st.expander("Trace why"):
                chain = chains[(idx - 1) % len(chains)]
                render_chain(chain["chain"])
                st.warning(f"This pattern may shift if {chain['low_confidence']} is replaced with observed data.")
    st.markdown("### Run snapshot")
    s = result["summary"]
    st.markdown(
        f"""
        <div class='metric-strip'>
          <div class='metric-card'><span class='source-badge system'>Simulated</span><h3>{s['dropoff_rate']*100:.1f}%</h3><b>Visits ending before completion</b><p>Visits that left before reaching the intended service outcome.</p></div>
          <div class='metric-card'><span class='source-badge system'>Simulated</span><h3>{s['conversion_rate']*100:.1f}%</h3><b>Visits reaching the intended outcome</b><p>Visits that completed the current target process.</p></div>
          <div class='metric-card'><span class='source-badge system'>Modelled signal</span><h3>{s['avg_clarity']}</h3><b>How often the next step felt clear</b><p>This is not a direct survey score.</p></div>
          <div class='metric-card'><span class='source-badge system'>Modelled signal</span><h3>{s['avg_trust']}</h3><b>How often the service felt credible</b><p>Based on current persona assumptions.</p></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_status_callout(
        "Use this finding as a direction, not a forecast",
        "Inspection time is a high-influence input and currently uses a system estimate. Add observed data before using this as an operational prediction.",
        "attention",
    )
    with st.expander("Compare all six personas"):
        rows = result.get("user_type_rows", [])
        persona_rows = []
        for i in range(6):
            raw = rows[i % len(rows)] if rows else {}
            persona_rows.append({"Persona": persona_profile({}, i)[0], **raw})
        st.dataframe(pd.DataFrame(persona_rows), use_container_width=True, hide_index=True)
    with st.expander("View technical details"):
        st.caption("Model version: Service Twin sandbox v0.8 · Current result is exploratory and assumption-led.")
        st.json({"main_dropoff_node": s.get("main_dropoff_node"), "reliability": "Medium-low"})
    if st.button("Try a change", type="primary", key="workflow_primary_try_change"):
        confirm("Adjustment path opened — change one thing and run again.", 5)
        goto_step(6)


def render_step6():
    render_page_intro(
        "Step 6 · Adjust",
        "Change one thing, run again",
        "Choose one factor from the trace. The rest of the service stays the same so you can see what this change may alter.",
    )
    params = st.session_state["params"]
    old = st.session_state.get("experience_result", {}).get("summary", {})
    st.markdown("### Suggested starting points")
    variable = st.radio(
        "Choose one factor",
        ["Inspection time", "Arrival rhythm", "Pricing conversation"],
        horizontal=True,
        key="adjust_variable",
        label_visibility="collapsed",
    )
    config = {
        "Inspection time": ("check_time_min", "Inspection duration", 3.0, 30.0, "min", "Wait for inspection and Device inspection"),
        "Arrival rhythm": ("arrival_rate_per_hour", "Arrival pace", 1.0, 60.0, "visits/hr", "Arrival and registration"),
        "Pricing conversation": ("transaction_time_min", "Pricing conversation duration", 1.0, 30.0, "min", "Pricing conversation and decision"),
    }
    key, label, low, high, unit, touches = config[variable]
    current_value = float(params[key])
    st.markdown(
        f"<div class='section-card'><div class='section-label'>Selected variable</div><h3>{label}</h3>"
        f"<p>Current value: <b>{current_value:g} {unit}</b></p><p>This change may be visible around: {touches}.</p>"
        f"{source_badge(st.session_state['param_sources'].get(key, 'System estimate'))}</div>",
        unsafe_allow_html=True,
    )
    params[key] = st.slider(f"New {label.lower()}", low, high, current_value, 1.0, key=f"adjust_{key}")
    render_status_callout(
        "Everything else stays the same",
        "Flow order, space zones, staff roles, scenario events, and the six persona definitions remain unchanged for this comparison.",
        "default",
    )
    st.markdown("### Make a larger change")
    path_cols = st.columns(4)
    if path_cols[0].button("Change the flow", use_container_width=True):
        goto_step(2)
    if path_cols[1].button("Change the space", use_container_width=True):
        goto_step(4)
    if path_cols[2].button("Change the personas", use_container_width=True):
        goto_step(3)
    if path_cols[3].button("Rebuild the scene", use_container_width=True):
        goto_step(1)
    if st.button("Run again with this change", type="primary", key="workflow_primary_run_again"):
        result = run_current_simulation(f"Adjusted {variable}")
        new = result["summary"]
        st.success(
            f"Queue recovery proxy changed from {old.get('avg_wait_min', 18)} min to {new.get('avg_wait_min', 9)} min. "
            f"Churn changed from {old.get('dropoff_rate', 0)*100:.1f}% to {new['dropoff_rate']*100:.1f}%."
        )
        st.markdown(
            f"<div class='delta-row'><div>Queue recovery time&nbsp; "
            f"<b>{old.get('avg_wait_min', 18)} min → {new.get('avg_wait_min', 9)} min</b> "
            f"<span class='delta-good'>▼</span></div>"
            f"<div>Reception pressure&nbsp; <b>High → High</b> <span class='delta-flat'>unchanged</span></div>"
            f"<div>Churn&nbsp; <b>{old.get('dropoff_rate', 0)*100:.1f}% → {new['dropoff_rate']*100:.1f}%</b></div></div>",
            unsafe_allow_html=True,
        )
        confirm("The comparison run is saved. Review the difference as a direction, not a claim that one version is best.", 6)


def render_sidebar():
    with st.sidebar:
        st.markdown("<div class='sidebar-nav-label'>Workflow navigation</div>", unsafe_allow_html=True)
        home_type = "primary" if st.session_state["screen"] == "home" else "secondary"
        if st.button("Home", key="workflow_nav_home", use_container_width=True, type=home_type):
            st.session_state["screen"] = "home"
            st.rerun()
        current_step = st.session_state["step"]
        visited_steps = st.session_state["visited_steps"]
        for step, label in STEP_LABELS.items():
            is_current = step == current_step
            is_visited = step in visited_steps
            if st.button(
                label,
                key=f"workflow_nav_{step}",
                use_container_width=True,
                disabled=not (is_current or is_visited),
                type="primary" if is_current else "secondary",
            ):
                goto_step(step)
        if st.session_state.get("step") == 3:
            render_persona_editor()


init_state()
apply_css()
render_progress()
st.caption(f"Build: {APP_BUILD} · Streamlit: {st.__version__}")

if st.session_state["screen"] == "home":
    render_home()
else:
    mark_step_visited(st.session_state["step"])
    render_sidebar()
    step = st.session_state["step"]
    if step == 1:
        render_step1()
    elif step == 2:
        render_step2()
    elif step == 3:
        render_step3()
    elif step == 4:
        render_step4()
    elif step == 5:
        render_step5()
    elif step == 6:
        render_step6()
