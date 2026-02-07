import streamlit as st
import yaml
import os
import json
from bot.ui_utils import render_sidebar, render_account_banner

# UI Setup
st.set_page_config(page_title="Feedback de Execução", layout="wide")
render_account_banner()

st.title("🛡️ Feedback de Execução & Pre-flight")

# Paths
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.yaml")
STATE_FILE = os.path.join(SCRIPT_DIR, "bot_state.json")

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def calculate_qty_ui(stop_dist, risk_cfg):
    if stop_dist <= 0: return 0
    equity = risk_cfg.get('account_equity', 100000)
    risk_pct = risk_cfg.get('risk_per_trade_percent', 1.0) / 100.0
    max_usd = risk_cfg.get('max_risk_usd', 500)
    risk_amt = min(equity * risk_pct, max_usd)
    return max(1, int(risk_amt / stop_dist))

config = load_config()
state = load_state()

st.markdown("""
Esta página fornece uma visão clara de quais ativos estão configurados para **execução real** vs. **apenas monitoramento**.
Use isso como um checklist antes de deixar o robô operando.
""")

if not config:
    st.error("Não foi possível carregar a configuração.")
else:
    trading_cfg = config.get('trading', {})
    symbols = trading_cfg.get('symbols', [])
    asset_strats = trading_cfg.get('asset_strategies', {})
    risk_pct = trading_cfg.get('risk_per_trade_percent', 0)
    max_usd = trading_cfg.get('max_risk_usd', 0)

    # Risk Summary Header
    with st.container(border=True):
        st.subheader("📊 Resumo de Risco Global")
        c1, c2 = st.columns(2)
        c1.metric("Risco por Operação (%)", f"{risk_pct}%")
        c2.metric("Teto de Perda (USD)", f"${max_usd:,.2f}")

    # Execution Lists
    col_live, col_obs = st.columns(2)

    with col_live:
        st.subheader("🚀 Ativos em EXECUÇÃO REAL")
        live_assets = [s for s in symbols if asset_strats.get(s) != "Monitor_Only"]
        if not live_assets:
            st.info("Nenhum ativo configurado para execução real.")
        else:
            for s in live_assets:
                strat = asset_strats.get(s, "ORB_5min")
                with st.expander(f"✅ **{s}** ({strat})", expanded=True):
                    s_data = state.get(s, {})
                    status = s_data.get('status', 'Aguardando...')
                    atr = s_data.get('atr', 0)
                    levels = s_data.get('levels')
                    
                    st.write(f"**Estratégia:** {strat}")
                    st.write(f"**Status Atual:** {status}")
                    
                    # Quantity Logic
                    estimated_qty = 0
                    reason = ""
                    
                    if strat == "ORB_5min":
                        if levels:
                            stop_dist = abs(levels.get('high', 0) - levels.get('low', 0))
                            estimated_qty = calculate_qty_ui(stop_dist, trading_cfg)
                            reason = "(Baseado no tamanho do 1º candle)"
                        elif atr > 0:
                            estimated_qty = calculate_qty_ui(atr, trading_cfg)
                            reason = "(Estimado por ATR enquanto aguarda ORB)"
                    elif strat == "VWAP_1min":
                        if atr > 0:
                            estimated_qty = calculate_qty_ui(atr, trading_cfg)
                            reason = "(Estimado por ATR para VWAP breakout)"
                    
                    if estimated_qty > 0:
                        st.metric("📦 Qtd. Estimada", f"{estimated_qty} un", help=reason)
                        st.caption(reason)
                    else:
                        st.warning("⚠️ Qtd. indisponível (Aguardando ATR/Níveis)")
                        
                    st.markdown("---")
                    st.caption("⚠️ O robô ENVIARÁ ordens reais para este ativo.")

    with col_obs:
        st.subheader("👁️ Ativos em MONITORAMENTO")
        obs_assets = [s for s in symbols if asset_strats.get(s) == "Monitor_Only"]
        if not obs_assets:
            st.info("Nenhum ativo configurado apenas para monitoramento.")
        else:
            for s in obs_assets:
                with st.expander(f"🔍 **{s}**", expanded=True):
                    s_data = state.get(s, {})
                    status = s_data.get('status', 'Aguardando...')
                    price = s_data.get('last_price', 0)
                    
                    st.write(f"**Status:** {status} | **Preço:** ${price:.2f}")
                    st.caption("ℹ️ Somente leitura. Nenhuma ordem será enviada.")

    st.divider()

    # Manual Execution Test Section
    from bot.ui_utils import place_manual_order, calc_quantity, calculate_capped_stop, fetch_last_candle
    
    with st.container(border=True):
        st.subheader("🧪 Teste de Execução Manual (Calculado)")
        st.markdown("Valide o dimensionamento de posição e o teto de stop baseado em ATR.")
        
        test_col1, test_col2, test_col3, test_col4 = st.columns([1.2, 1, 1, 1])
        
        with test_col1:
            symbol_options = sorted(symbols) if symbols else []
            test_symbol = st.selectbox("Ativo", options=symbol_options, key="manual_test_symbol")
            
            # Auto-fetch logic on symbol change
            if "last_test_symbol" not in st.session_state or st.session_state.last_test_symbol != test_symbol:
                st.session_state.last_test_symbol = test_symbol
                tf = trading_cfg.get('timeframe', '5 mins')
                # Use a small spinner for the fetch
                with st.status(f"Buscando último candle ({tf}) for {test_symbol}...", expanded=False):
                    recovered = fetch_last_candle(test_symbol, bar_size=tf)
                    if recovered:
                        st.session_state[f"h_{test_symbol}"] = recovered['high']
                        st.session_state[f"l_{test_symbol}"] = recovered['low']
                        st.session_state[f"o_{test_symbol}"] = recovered['open']
                        st.session_state[f"c_{test_symbol}"] = recovered['close']
                        st.session_state[f"start_{test_symbol}"] = recovered['start_time']
                        st.session_state[f"end_{test_symbol}"] = recovered['end_time']
            
            s_data = state.get(test_symbol, {})
            current_price = s_data.get('last_price', 0.0)
            current_atr = s_data.get('atr', 0.0)
            levels = s_data.get('levels') or {}

        with test_col2:
            entry_price = st.number_input("Preço de Entrada", value=float(current_price), step=0.01, format="%.2f")
        
        with test_col3:
            raw_stop = st.number_input("Stop Manual", value=float(entry_price * 0.99), step=0.01, format="%.2f")
            
        with test_col4:
            atr_val = st.number_input("ATR (14d)", value=float(current_atr), step=0.01, format="%.2f")

        # Candle Data & Schematic Section
        st.markdown("---")
        candle_data_col, schematic_col = st.columns([2, 1])
        
        with candle_data_col:
            st.write("**Dados do Último Candle (Automático):**")
            
            # Get values from session state or levels
            c_high = st.session_state.get(f"h_{test_symbol}", levels.get('high', entry_price * 1.01))
            c_low = st.session_state.get(f"l_{test_symbol}", levels.get('low', entry_price * 0.99))
            c_open = st.session_state.get(f"o_{test_symbol}", levels.get('open', entry_price))
            c_close = st.session_state.get(f"c_{test_symbol}", levels.get('close', entry_price))
            c_start = st.session_state.get(f"start_{test_symbol}", "N/A")
            c_end = st.session_state.get(f"end_{test_symbol}", "N/A")
            
            # Display Timestamps
            st.markdown(f"🕒 **Início:** `{c_start}` | 🏁 **Fim:** `{c_end}`")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("High", f"{c_high:.2f}")
            c2.metric("Low", f"{c_low:.2f}")
            c3.metric("Open", f"{c_open:.2f}")
            c4.metric("Close", f"{c_close:.2f}")
            
            if st.button("🔄 Forçar Recarga", help="Recarrega o candle mais recente agora"):
                tf = trading_cfg.get('timeframe', '5 mins')
                recovered = fetch_last_candle(test_symbol, bar_size=tf)
                if recovered:
                    st.session_state[f"h_{test_symbol}"] = recovered['high']
                    st.session_state[f"l_{test_symbol}"] = recovered['low']
                    st.session_state[f"o_{test_symbol}"] = recovered['open']
                    st.session_state[f"c_{test_symbol}"] = recovered['close']
                    st.session_state[f"start_{test_symbol}"] = recovered['start_time']
                    st.session_state[f"end_{test_symbol}"] = recovered['end_time']
                    st.rerun()

        with schematic_col:
            # Simple CSS Schematic Candle
            is_bullish = c_close >= c_open
            color = "#26a69a" if is_bullish else "#ef5350"
            body_top_val = max(c_open, c_close)
            body_bottom_val = min(c_open, c_close)
            
            # Normalize for visualization (0-100px range)
            range_total = c_high - c_low if c_high > c_low else 0.01
            
            def normalize(v):
                clamped = max(c_low, min(c_high, v))
                return 100 - ((clamped - c_low) / range_total * 100)
            
            w_top = normalize(c_high)
            w_bottom = normalize(c_low)
            b_top = normalize(body_top_val)
            b_bottom = normalize(body_bottom_val)
            body_height = b_bottom - b_top
            
            st.markdown(f"""
            <div style="display: flex; flex-direction: column; align-items: center; background: #1e1e1e; padding: 10px; border-radius: 5px; height: 120px; width: 100%; position: relative; border: 1px solid #333;">
                <div style="position: absolute; top: {w_top + 10}px; height: {w_bottom - w_top}px; width: 2px; background: #888;"></div>
                <div style="position: absolute; top: {b_top + 10}px; height: {max(2, body_height)}px; width: 20px; background: {color}; border: 1px solid #fff3;"></div>
            </div>
            <div style="text-align: center; width: 100%; font-size: 0.7rem; color: #888; margin-top: 5px;">Esquemático ({trading_cfg.get('timeframe', '5m')})</div>
            """, unsafe_allow_html=True)

        # Interactive Preview & Direction
        st.markdown("---")
        res_col, dir_col = st.columns([2, 1])
        
        with dir_col:
            test_side = st.radio("Direção", ["BUY", "SELL"], horizontal=True)
            
        max_stop_atr = trading_cfg.get('max_stop_atr', 0.0)
        final_stop = calculate_capped_stop(entry_price, raw_stop, test_side, atr_val, max_stop_atr)
        stop_dist = abs(entry_price - final_stop)
        
        final_qty = calc_quantity(stop_dist, trading_cfg)
        
        with res_col:
            res_c1, res_c2, res_c3 = st.columns(3)
            res_c1.metric("📦 Qtd. Calculada", f"{final_qty} un")
            
            stop_color = "normal"
            if final_stop != raw_stop:
                stop_color = "inverse"
                res_c2.metric("🛡️ Stop Capped (ATR)", f"${final_stop:.2f}", delta="Limitado", delta_color=stop_color)
            else:
                res_c2.metric("🛡️ Stop Final", f"${final_stop:.2f}")
                
            res_c3.metric("📉 Risco Total", f"${(stop_dist * final_qty):.2f}")

        # Breakdown Expander
        with st.expander("📝 Detalhes do Cálculo"):
            equity = trading_cfg.get('account_equity', 100000)
            risk_pct = trading_cfg.get('risk_per_trade_percent', 1.0)
            max_risk_usd = trading_cfg.get('max_risk_usd', 500)
            calculated_risk = min(equity * (risk_pct/100), max_risk_usd)
            
            st.markdown(f"""
            **1. Risco por Operação:**
            - Patrimônio: `${equity:,.2f}` | Risco: `{risk_pct}%`
            - Teto USD Configurado: `${max_risk_usd:,.2f}`
            - **Risco Efetivo:** `${calculated_risk:,.2f}` (Menor valor entre % do patrimônio e teto USD)

            **2. Limite de Stop (Capping ATR):**
            - Multiplicador Max Stop: `{max_stop_atr}x ATR`
            - ATR(14d): `{atr_val:.2f}` | Limite de Distância: `{atr_val * max_stop_atr:.2f}`
            - Distância Manual: `{abs(entry_price - raw_stop):.2f}`
            - **Stop Final:** `${final_stop:.2f}` {"(Limitado pelo ATR)" if final_stop != raw_stop else "(Dentro do limite)"}

            **3. Dimensionamento Final:**
            - Fórmula: `Risco Efetivo / Distância do Stop Final`
            - Conta: `{calculated_risk:,.2f} / {stop_dist:.2f}`
            - **Quantidade:** `{final_qty} un`
            """)

        st.divider()
        
        b_col1, b_col2 = st.columns(2)
        
        if b_col1.button("🚀 Enviar Market", use_container_width=True, type="secondary"):
            if test_symbol and final_qty > 0:
                success, msg = place_manual_order(test_symbol, final_qty, order_type='MARKET', side=test_side)
                if success: st.success(msg)
                else: st.error(msg)
            else: st.warning("Dados inválidos.")

        if b_col2.button("📦 Enviar Bracket (Entry + Stop)", use_container_width=True, type="primary"):
            if test_symbol and final_qty > 0:
                success, msg = place_manual_order(test_symbol, final_qty, order_type='BRACKET', side=test_side, stop_price=final_stop)
                if success: st.success(msg)
                else: st.error(msg)
            else: st.warning("Dados inválidos.")

# Sidebar
render_sidebar()
st.sidebar.info("Confirme sempre seus ativos antes de iniciar o pregão.")
