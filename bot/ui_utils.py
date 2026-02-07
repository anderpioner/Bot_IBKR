import streamlit as st
import json
import os
import subprocess
import psutil
import time
import yaml
from datetime import datetime, timedelta
import pytz
import asyncio
import nest_asyncio

# CRITICAL: Create/Set event loop BEFORE importing ib_insync
# eventkit (dependency of ib_insync) crashes at import if no loop exists
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())
nest_asyncio.apply()

from ib_insync import IB, Stock, MarketOrder, StopOrder

def calc_quantity(stop_distance: float, risk_config: dict):
    """Calculate quantity based on risk % and stop distance"""
    if stop_distance <= 0:
        return 0
        
    equity = risk_config.get('account_equity', 100000)
    risk_pct = risk_config.get('risk_per_trade_percent', 1.0) / 100.0
    max_risk_usd = risk_config.get('max_risk_usd', 500)
    
    risk_amt = min(equity * risk_pct, max_risk_usd)
    
    quantity = int(risk_amt / stop_distance)
    return max(1, quantity)

def calculate_capped_stop(entry_price: float, raw_stop: float, side: str, atr: float, max_stop_atr: float):
    """Apply ATR-based stop loss limit"""
    if max_stop_atr <= 0 or atr <= 0:
        return raw_stop

    atr_limit_dist = atr * max_stop_atr
    raw_dist = abs(entry_price - raw_stop)
    
    if raw_dist > atr_limit_dist:
        capped_stop = entry_price - atr_limit_dist if side == 'BUY' else entry_price + atr_limit_dist
        return round(capped_stop, 2)
        
    return round(raw_stop, 2)

def place_manual_order(symbol, quantity, order_type='MARKET', side='BUY', stop_price=None, transmit=True):
    """Sends a manual order to IBKR for testing"""
    config = load_config()
    ibkr_params = config.get('ibkr', {})
    
    ib = IB()
    try:
        # Use a different client_id for manual orders to avoid conflicts
        ib.connect(ibkr_params.get('host', '127.0.0.1'), 
                   ibkr_params.get('port', 7497), 
                   clientId=99)
        
        contract = Stock(symbol, 'SMART', 'USD')
        ib.qualifyContracts(contract)
        
        if order_type == 'MARKET':
            order = MarketOrder(side, quantity)
            order.transmit = transmit
            trade = ib.placeOrder(contract, order)
            return True, f"Ordem MARKET de {side} enviada para {symbol} ({quantity} un)."
            
        elif order_type == 'BRACKET' and stop_price:
            parent = MarketOrder(side, quantity)
            parent.transmit = False # Wait for child
            
            # Side for stop is opposite of entry
            stop_side = 'SELL' if side == 'BUY' else 'BUY'
            stop_order = StopOrder(stop_side, quantity, stop_price)
            stop_order.parentId = parent.orderId
            stop_order.transmit = transmit
            
            ib.placeOrder(contract, parent)
            ib.placeOrder(contract, stop_order)
            return True, f"Ordem BRACKET enviada para {symbol}. Entrada {side} Market + Stop em {stop_price}."
            
        return False, "Tipo de ordem não suportado."
    except Exception as e:
        return False, f"Falha na execução: {e}"
    finally:
        if ib.isConnected():
            ib.disconnect()

def fetch_last_candle(symbol, bar_size='5 mins'):
    """Fetches the OHLC of the very last bar from IBKR"""
    config = load_config()
    ibkr_params = config.get('ibkr', {})
    
    ib = IB()
    try:
        ib.connect(ibkr_params.get('host', '127.0.0.1'), 
                   ibkr_params.get('port', 7497), 
                   clientId=98) # Unique ID for data fetch
        
        contract = Stock(symbol, 'SMART', 'USD')
        ib.qualifyContracts(contract)
        
        # Request only 1 bar
        duration = '1800 S' if 'min' in bar_size else '1 D'
        bars = ib.reqHistoricalData(
            contract, endDateTime='', durationStr=duration,
            barSizeSetting=bar_size, whatToShow='TRADES', useRTH=True)
        
        if bars:
            last = bars[-1]
            start_time = last.date
            
            # Parse minutes from bar_size (e.g., '5 mins' -> 5)
            try:
                mins = int(bar_size.split()[0]) if 'min' in bar_size else 0
                if 'day' in bar_size:
                    end_time = start_time + timedelta(days=1)
                else:
                    end_time = start_time + timedelta(minutes=mins)
            except:
                end_time = start_time

            return {
                'high': last.high,
                'low': last.low,
                'open': last.open,
                'close': last.close,
                'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S') if hasattr(start_time, 'strftime') else str(start_time),
                'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S') if hasattr(end_time, 'strftime') else str(end_time)
            }
        return None
    except Exception as e:
        print(f"Error fetching candle for {symbol}: {e}")
        return None
    finally:
        if ib.isConnected():
            ib.disconnect()

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(SCRIPT_DIR, "bot_state.json")

def get_ny_time():
    """Returns the current time in New York"""
    ny_tz = pytz.timezone('America/New_York')
    return datetime.now(ny_tz)

def load_config():
    config_path = os.path.join(SCRIPT_DIR, "config.yaml")
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except:
        return {}

def render_account_banner():
    """Renders the account type banner (Brown/Blue) at the top of the page"""
    config = load_config()
    acc_type = config.get('ibkr', {}).get('account_type', 'paper')
    
    # Banner CSS
    banner_color = "#8B4513" if acc_type == 'paper' else "#1E90FF"
    banner_text = "MODO: PAPER TRADING" if acc_type == 'paper' else "MODO: CONTA REAL"

    st.markdown(f"""
        <style>
        .account-banner {{
            background-color: {banner_color};
            color: white;
            text-align: center;
            padding: 5px;
            font-weight: bold;
            border-radius: 5px;
            margin-bottom: 20px;
            font-size: 1.2rem;
            width: 100%;
        }}
        </style>
        <div class="account-banner">
            {banner_text}
        </div>
        """, unsafe_allow_html=True)

def load_bot_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def find_bot_process():
    """Finds the bot process (main.py)"""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline')
            if cmdline and any('main.py' in arg for arg in cmdline):
                return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None

def start_bot():
    """Starts the bot in a new console window"""
    try:
        # Get absolute path to main.py
        bot_script = os.path.join(SCRIPT_DIR, "main.py")
        # Run in a new console window on Windows
        subprocess.Popen(["python", bot_script], creationflags=subprocess.CREATE_NEW_CONSOLE, cwd=SCRIPT_DIR)
        return True
    except Exception as e:
        st.error(f"Erro ao iniciar o robô: {e}")
        return False

def stop_bot():
    """Stops the bot process"""
    proc = find_bot_process()
    if proc:
        try:
            proc.terminate()
            return True
        except Exception as e:
            st.error(f"Erro ao parar o robô: {e}")
            return False
    return False

def render_sidebar():
    """Shared sidebar for all pages with status indicators"""
    st.sidebar.title("🎲 Navegação")
    st.sidebar.page_link("dashboard.py", label="📈 Monitoramento", icon="📊")
    st.sidebar.page_link("pages/1_Configuration.py", label="⚙️ Configurações", icon="🛠️")
    st.sidebar.page_link("pages/2_Execution_Feedback.py", label="🛡️ Feedback de Execução", icon="🛡️")
    
    st.sidebar.divider()
    
    # Connection Status
    state_data = load_bot_state()
    bot_info = state_data.get("_bot_info", {})
    last_update_str = bot_info.get("last_update")
    is_connected = bot_info.get("is_connected", False)
    server_time_str = bot_info.get("server_time")
    
    status_label = "🔴 Offline"
    ny_tz = pytz.timezone('America/New_York')
    ny_time = datetime.now(ny_tz)
    
    if last_update_str:
        last_update = datetime.fromisoformat(last_update_str)
        if datetime.now() - last_update < timedelta(seconds=15):
            status_label = "🟢 Online" if is_connected else "🟡 Standby (No API)"
            if server_time_str and is_connected:
                # Convert the UTC server time to NY time
                st_dt = datetime.fromisoformat(server_time_str)
                ny_time = st_dt.astimezone(ny_tz)
            
    # Market Status Indicator
    is_open = False
    if ny_time.weekday() < 5: # Mon-Fri
        market_open = ny_time.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = ny_time.replace(hour=16, minute=0, second=0, microsecond=0)
        if market_open <= ny_time <= market_close:
            is_open = True
    market_status = "🟢" if is_open else "🔴"
    
    # Combined Status Section
    st.sidebar.subheader("🤖 Status & Ambiente")
    
    col_status1, col_status2 = st.sidebar.columns(2)
    col_status1.markdown(f"**IBKR:** {status_label}")
    col_status2.markdown(f"**Mkt:** {market_status}")
    
    st.sidebar.markdown(f"**NY:** `{ny_time.strftime('%H:%M:%S')}`")
    
    # Account Switch (Condensado)
    config_path = os.path.join(SCRIPT_DIR, "config.yaml")
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        acc_type = config.get('ibkr', {}).get('account_type', 'paper')
        if acc_type == 'paper':
            if st.sidebar.button("🔵 Switch to REAL", use_container_width=True, help="Muda para Conta Real (Porta 7496)"):
                config['ibkr']['account_type'] = 'real'
                config['ibkr']['port'] = 7496
                with open(config_path, 'w') as f:
                    yaml.safe_dump(config, f)
                st.sidebar.success("Modo Real!")
                time.sleep(0.5)
                st.rerun()
        else:
            if st.sidebar.button("🟤 Switch to PAPER", use_container_width=True, help="Muda para Paper Trading (Porta 7497)"):
                config['ibkr']['account_type'] = 'paper'
                config['ibkr']['port'] = 7497
                with open(config_path, 'w') as f:
                    yaml.safe_dump(config, f)
                st.sidebar.success("Modo Paper!")
                time.sleep(0.5)
                st.rerun()
    except Exception as e:
        st.sidebar.error(f"Erro config: {e}")

    st.sidebar.divider()

    # Bot Control Section
    st.sidebar.subheader("🎮 Controle do Robô")
    bot_proc = find_bot_process()
    
    if bot_proc:
        st.sidebar.success(f"Robô em Execução (PID: {bot_proc.pid})")
        if st.sidebar.button("🛑 Parar Robô", use_container_width=True, type="primary"):
            if stop_bot():
                st.sidebar.success("Sinal de parada enviado.")
                time.sleep(1)
                st.rerun()
    else:
        st.sidebar.warning("Robô não está rodando.")
        if st.sidebar.button("🚀 Iniciar Robô", use_container_width=True, type="primary"):
            if start_bot():
                st.sidebar.success("Iniciando robô...")
                time.sleep(1)
                st.rerun()

    st.sidebar.divider()
    if st.sidebar.button("🔄 Atualizar UI", use_container_width=True):
        st.rerun()
