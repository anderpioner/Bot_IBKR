import os
import asyncio
import yaml
import logging
import json
from datetime import datetime
import nest_asyncio
from ib_insync import IB, Stock, util, MarketOrder, StopOrder, LimitOrder
from bot.connection import IBConnection
from bot.models import TradeState, ORBLevels
from bot.strategies.orb_5min import ORB5MinStrategy
from bot.strategies.vwap_1min import VWAP1MinStrategy
from bot.strategies.monitor_only import MonitorOnlyStrategy

STRATEGIES = {
    'ORB_5min': ORB5MinStrategy,
    'VWAP_1min': VWAP1MinStrategy,
    'Monitor_Only': MonitorOnlyStrategy
}

# Set up logging
base_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(base_dir, "bot.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("IBKRBot")

class ORBBot:
    def __init__(self, config_path="config.yaml"):
        self.config_path = config_path
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.states = {symbol: TradeState(symbol=symbol) for symbol in self.config['trading']['symbols']}
        self.active_strategies = {}
        
        # Use absolute path for state file
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.state_file = os.path.join(base_dir, "bot_state.json")
        self.config_mtime = os.path.getmtime(self.config_path)
        
        self.is_running = False

    def save_state(self):
        try:
            state_data = {}
            for symbol, state in self.states.items():
                d = state.to_dict()
                # Find the strategy name assigned to this symbol
                strategy_name = "Unknown"
                if symbol in self.active_strategies:
                    strategy_name = self.active_strategies[symbol].__class__.__name__.replace("Strategy", "")
                d["strategy"] = strategy_name
                state_data[symbol] = d
                
            server_time = None
            is_connected = self.ib.isConnected() if self.ib else False
            if is_connected:
                # get server time
                server_time = self.ib.reqCurrentTime().isoformat()

            state_data["_bot_info"] = {
                "last_update": datetime.now().isoformat(),
                "is_connected": is_connected,
                "server_time": server_time
            }
            with open(self.state_file, "w") as f:
                json.dump(state_data, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving state: {e}")

    async def run(self):
        nest_asyncio.apply()
        self.conn = IBConnection(
            host=self.config['ibkr']['host'],
            port=self.config['ibkr']['port'],
            client_id=self.config['ibkr']['client_id']
        )
        self.ib = self.conn.ib
        
        if not await self.conn.connect():
            logger.error("Could not connect to TWS/Gateway. Please ensure it is running and API settings are correct.")
            print("\n" + "!"*50)
            print("ERRO DE CONEXÃO: O TWS não está rodando ou a porta está incorreta.")
            print("!"*50 + "\n")
            input("Pressione ENTER para fechar esta janela...")
            return
        
        self.ib = self.conn.ib # Update reference after connection

        self.is_running = True
        self.save_state() # Signal Online status immediately after connection
        
        logger.info("Bot started. Monitoring assets...")
        
        # Subscribe TO ONCE for all assets
        self.ib.pendingTickersEvent += self.on_ticker_update
        
        # Request data for each asset
        for symbol, state in self.states.items():
            contract = Stock(symbol, 'SMART', 'USD')
            await self.ib.qualifyContractsAsync(contract)
            
            # Subscribe to real-time bars
            self.ib.reqMktData(contract)
            
            # Subscribe to bars
            bars = self.ib.reqHistoricalData(
                contract, endDateTime='', durationStr='1 D',
                barSizeSetting='1 min', whatToShow='TRADES', useRTH=True, keepUpToDate=True)
            bars.updateEvent += self.on_bar_update
            
            # Initialize Strategy
            strategy_name = self.config['trading'].get('strategy', 'ORB_5min')
            strategy_name = self.config['trading'].get('asset_strategies', {}).get(symbol, strategy_name)
            
            StrategyClass = STRATEGIES.get(strategy_name, ORB5MinStrategy)
            risk_config = self.config['trading']
            self.active_strategies[symbol] = StrategyClass(self.ib, state, risk_config)
            
            logger.info(f"Initializing strategy for {symbol}...")
            try:
                await asyncio.wait_for(self.active_strategies[symbol].initialize(), timeout=30)
                state.add_log(f"Started monitoring {symbol} with {strategy_name}")
            except asyncio.TimeoutError:
                logger.error(f"Timeout initializing {symbol}. Skipping for now.")
            except Exception as e:
                logger.error(f"Error initializing {symbol}: {e}")
        
        try:
            while self.is_running:
                await self.check_config_update()
                self.save_state()
                await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            logger.error(f"Error in main loop: {e}")
        finally:
            self.is_running = False
            if self.conn:
                self.conn.disconnect()
            self.save_state() # Save final disconnected state

    def on_ticker_update(self, tickers):
        for ticker in tickers:
            symbol = ticker.contract.symbol
            if symbol not in self.active_strategies: continue
            
            last_price = ticker.last if ticker.last == ticker.last else ticker.close
            self.states[symbol].last_price = last_price
            self.active_strategies[symbol].on_ticker_update(last_price, ticker)

    def on_bar_update(self, bars, has_new_bar: bool):
        symbol = bars.contract.symbol
        if symbol in self.active_strategies:
            asyncio.create_task(self.active_strategies[symbol].on_bar_update(bars, has_new_bar))

    async def check_config_update(self):
        current_mtime = os.path.getmtime(self.config_path)
        if current_mtime > self.config_mtime:
            logger.info("Config change detected. Reloading symbols...")
            self.config_mtime = current_mtime
            
            with open(self.config_path, 'r') as f:
                new_config = yaml.safe_load(f)
            
            new_symbols = set(new_config['trading']['symbols'])
            current_symbols = set(self.states.keys())

            # Add new symbols
            for symbol in new_symbols - current_symbols:
                logger.info(f"Adding new asset to monitor: {symbol}")
                self.states[symbol] = TradeState(symbol=symbol)
                contract = Stock(symbol, 'SMART', 'USD')
                await self.ib.qualifyContractsAsync(contract)
                
                # Initialize strategy
                strategy_name = new_config['trading'].get('strategy', 'ORB_5min')
                strategy_name = new_config['trading'].get('asset_strategies', {}).get(symbol, strategy_name)
                
                StrategyClass = STRATEGIES.get(strategy_name, ORB5MinStrategy)
                risk_config = new_config['trading']
                self.active_strategies[symbol] = StrategyClass(self.ib, self.states[symbol], risk_config)
                
                try:
                    await asyncio.wait_for(self.active_strategies[symbol].initialize(), timeout=30)
                    self.states[symbol].add_log(f"Dynamic subscription started for {symbol} ({strategy_name})")
                except asyncio.TimeoutError:
                    logger.error(f"Timeout dynamic initializing {symbol}. Skipping.")
                except Exception as e:
                    logger.error(f"Error dynamic initializing {symbol}: {e}")

            # Remove symbols
            for symbol in current_symbols - new_symbols:
                logger.info(f"Removing asset: {symbol}")
                if symbol in self.active_strategies:
                    del self.active_strategies[symbol]
                del self.states[symbol]
            
            self.save_state()

    def stop(self):
        self.is_running = False

if __name__ == "__main__":
    try:
        bot = ORBBot()
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\nBot encerrado pelo usuário.")
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        input("\nPressione ENTER para sair...")
