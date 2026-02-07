import streamlit as st
import yaml
import os
import time
import json
from bot.ui_utils import render_sidebar, render_account_banner

# UI Setup
st.set_page_config(page_title="Configurações do Robô", layout="wide")
render_account_banner()

st.title("⚙️ Configurações de Ativos e Estratégias")

# Paths
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.yaml")
STATE_FILE = os.path.join(SCRIPT_DIR, "bot_state.json")

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

def save_config(symbols, asset_strategies, risk_params, ibkr_params):
    config = load_config()
    config['trading']['symbols'] = [s.strip().upper() for s in symbols.split(',') if s.strip()]
    config['trading']['asset_strategies'] = asset_strategies
    config['trading'].update(risk_params)
    config['ibkr'].update(ibkr_params)
    with open(CONFIG_FILE, 'w') as f:
        yaml.safe_dump(config, f)
    return config

current_config = load_config()

st.markdown("""
Nesta página você pode definir quais ativos o robô deve monitorar e qual estratégia aplicar a cada um deles.
As mudanças são detectadas automaticamente pelo robô assim que você clicar em **Salvar**.
""")

with st.container(border=True):
    con_col1, con_col2, con_col3 = st.columns([1, 2, 1], vertical_alignment="center")
    con_col1.markdown("### 🔌 Conexão")
    current_acc_type = current_config['ibkr'].get('account_type', 'paper')
    label = "🟤 Paper" if current_acc_type == 'paper' else "🔵 Real"
    con_col2.write(f"**Modo:** {label}")
    with con_col3:
        port = st.number_input("Porta", value=int(current_config['ibkr'].get('port', 7497)), step=1, label_visibility="collapsed")
    
    ibkr_params = {'account_type': current_acc_type, 'port': port}

with st.container(border=True):
    r_col1, r_col2, r_col3, r_col4, r_col5 = st.columns([1, 1, 1, 1, 1.5], vertical_alignment="center")
    r_col1.markdown("### 📊 Risco")
    with r_col2:
        risk_pct = st.number_input("R% ", min_value=0.1, max_value=10.0, value=float(current_config['trading'].get('risk_per_trade_percent', 1.0)), step=0.1)
    with r_col3:
        equity = st.number_input("Acc $ ", min_value=1000, value=int(current_config['trading'].get('account_equity', 100000)), step=1000)
    with r_col4:
        max_stop_atr = st.number_input("Stop ATR ", min_value=0.0, max_value=2.0, value=float(current_config['trading'].get('max_stop_atr', 0.0)), step=0.01)
    
    calculated_max_usd = equity * (risk_pct / 100.0)
    r_col5.metric("Risco Max USD", f"${calculated_max_usd:,.2f}")

st.divider()

with st.container(border=True):
    st.subheader("🔍 Ativos em Monitoramento")
    symbols_str = ", ".join(current_config['trading']['symbols'])
    new_symbols = st.text_area("Lista de Símbolos (separados por vírgula)", value=symbols_str, help="Ex: AAPL, TSLA, NVDA, MSFT")
    
    st.divider()
    
    st.subheader("🎯 Estratégias por Ativo")
    asset_strategies = current_config['trading'].get('asset_strategies', {})
    bot_state = load_state()
    new_asset_strategies = {}
    
    active_symbols = [s.strip().upper() for s in new_symbols.split(',') if s.strip()]
    
    if not active_symbols:
        st.warning("Nenhum ativo inserido na lista acima.")
    else:
        # Create Table Header
        hcol1, hcol2, hcol3, hcol4 = st.columns([1, 1, 1, 2])
        hcol1.markdown("**Ativo**")
        hcol2.markdown("**Preço Atual**")
        hcol3.markdown("**ATR (14)**")
        hcol4.markdown("**Estratégia**")
        st.divider()

        for symbol in active_symbols:
            state = bot_state.get(symbol, {})
            price = state.get("last_price", 0.0)
            atr = state.get("atr", 0.0)
            
            row_col1, row_col2, row_col3, row_col4 = st.columns([1, 1, 1, 2])
            
            row_col1.write(f"**{symbol}**")
            row_col2.write(f"${price:.2f}" if price > 0 else "N/A")
            row_col3.write(f"{atr:.2f}" if atr > 0 else "N/A")
            
            current_strategy = asset_strategies.get(symbol, current_config['trading'].get('strategy', 'ORB_5min'))
            options = ['ORB_5min', 'VWAP_1min', 'Monitor_Only']
            try:
                default_index = options.index(current_strategy)
            except ValueError:
                default_index = 0
                
            choice = row_col4.selectbox(f"Select_{symbol}", options=options, 
                                 index=default_index,
                                 key=f"strat_{symbol}",
                                 label_visibility="collapsed")
            new_asset_strategies[symbol] = choice

    st.divider()
    
    if st.button("💾 Salvar Configurações", use_container_width=True, type="primary"):
        risk_params = {
            'risk_per_trade_percent': risk_pct,
            'account_equity': equity,
            'max_risk_usd': calculated_max_usd,
            'max_stop_atr': max_stop_atr
        }
        save_config(new_symbols, new_asset_strategies, risk_params, ibkr_params)
        st.success("✅ Configurações salvas com sucesso! O robô será atualizado em instantes.")
        time.sleep(2)
        st.rerun()

st.divider()

# Sizing Simulator for Testing
with st.container(border=True):
    st.subheader("🧮 Simulador de Dimensionamento (Teste)")
    st.markdown("Use este simulador para testar se a quantidade de ações está sendo calculada corretamente conforme seu risco.")
    
    sim_col1, sim_col2, sim_col3 = st.columns(3)
    
    with sim_col1:
        test_entry = st.number_input("Preço de Entrada ($)", min_value=0.01, value=150.0, step=0.1)
    with sim_col2:
        test_stop = st.number_input("Preço de Stop Loss ($)", min_value=0.01, value=148.0, step=0.1)
    
    current_atr = 5.0 # Example ATR for simulator
    stop_dist = abs(test_entry - test_stop)
    
    # Apply ATR Limit in simulator if enabled
    is_capped = False
    final_stop_dist = stop_dist
    if max_stop_atr > 0:
        atr_limit = current_atr * max_stop_atr
        if stop_dist > atr_limit:
            final_stop_dist = atr_limit
            is_capped = True
    
    if final_stop_dist <= 0:
        st.error("A entrada e o stop não podem ser iguais.")
    else:
        # Re-calculate using current UI values
        sim_max_risk = equity * (risk_pct / 100.0)
        sim_qty = int(sim_max_risk / final_stop_dist)
        sim_final_qty = max(1, sim_qty)
        
        with sim_col3:
            st.metric("Quantidade de Ações", f"{sim_final_qty} un")
            if is_capped:
                st.caption(f"⚠️ Stop limitado a {max_stop_atr} ATR (${final_stop_dist:.2f})")
            
        st.info(f"**Explicação do Cálculo:** Com um risco de **${sim_max_risk:,.2f}** e uma distância de stop de **${final_stop_dist:.2f}** {'(limitada pelo ATR)' if is_capped else ''}, o sistema comprará **{sim_final_qty}** ações.")

# Sidebar
render_sidebar()

st.sidebar.info("As configurações afetarão o robô que está rodando no terminal.")
