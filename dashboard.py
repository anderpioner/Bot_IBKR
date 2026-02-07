import streamlit as st
import pandas as pd
import json
import time
import os
import yaml
from datetime import datetime, timedelta
from bot.ui_utils import render_sidebar, render_account_banner

# UI Setup
st.set_page_config(page_title="IBKR ORB/VWAP Bot Dashboard", layout="wide")
render_account_banner()

st.title("🛡️ IBKR Multi-Strategy Bot")

# Ensure absolute path for the config and state
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, "bot_state.json")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.yaml")

def load_state():
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error loading state: {e}")
        return None

state_data = load_state()

# Sidebar
render_sidebar()

# Layout
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Active Monitoring")
    if state_data:
        table_data = []
        for key, value in state_data.items():
            if key.startswith("_"): continue
            
            levels = value.get("levels") or {}
            table_data.append({
                "Asset": value.get("symbol"),
                "Strategy": value.get("strategy", "N/A"),
                "Status": value.get("status"),
                "ORB/Sig High": f"{levels.get('high'):.2f}" if levels.get('high') else "N/A",
                "ORB/Sig Low": f"{levels.get('low'):.2f}" if levels.get('low') else "N/A",
                "Entry": f"{value.get('entry_price'):.2f}" if value.get('entry_price') else "N/A",
                "Stop Loss": f"{value.get('stop_loss'):.2f}" if value.get('stop_loss') else "N/A",
                "Pos": value.get("position")
            })
        
        df = pd.DataFrame(table_data)
        st.table(df)
    else:
        st.info("Waiting for bot to start and save state...")

with col2:
    st.subheader("Logs")
    if state_data:
        all_logs = []
        for key, value in state_data.items():
            if key.startswith("_"): continue
            symbol = value.get("symbol")
            for log in value.get("logs", []):
                all_logs.append(f"{symbol}: {log}")
        
        st.text_area("Console", value="\n".join(all_logs[-25:]), height=500, key="console")
    else:
        st.text_area("Console", value="No logs.", height=500)

# Auto-refresh
time.sleep(2)
st.rerun()
