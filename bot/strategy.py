from abc import ABC, abstractmethod
import time
from bot.models import TradeState
from ib_insync import IB, Stock
from bot.ui_utils import calc_quantity, calculate_capped_stop

class BaseStrategy(ABC):
    def __init__(self, ib: IB, state: TradeState, risk_config: dict = None):
        self.ib = ib
        self.state = state
        self.risk_config = risk_config or {}
        self.symbol = state.symbol
        self.contract = Stock(self.symbol, 'SMART', 'USD')
        self.last_atr_update = 0

    async def initialize(self):
        """Initial data fetching like ORB levels or historical ATR"""
        await self.update_atr()

    async def update_atr(self):
        """Fetch 14 days of daily bars to calculate ATR(14)"""
        try:
            bars = await self.ib.reqHistoricalDataAsync(
                self.contract, endDateTime='', durationStr='30 D',
                barSizeSetting='1 day', whatToShow='TRADES', useRTH=True)
            
            if len(bars) < 15:
                self.state.atr = 0.0
                return

            # Simple ATR calculation
            tr_list = []
            for i in range(1, len(bars)):
                h = bars[i].high
                l = bars[i].low
                pc = bars[i-1].close
                tr = max(h - l, abs(h - pc), abs(l - pc))
                tr_list.append(tr)
            
            # Use last 14 TRs
            atr_14 = sum(tr_list[-14:]) / 14
            self.state.atr = atr_14
            
            # Populate initial price if it's currently 0
            if self.state.last_price == 0:
                self.state.last_price = bars[-1].close
                
            self.add_log(f"ATR(14) calculated: {self.state.atr:.2f}")
        except Exception as e:
            self.add_log(f"Error calculating ATR: {e}")
        finally:
            self.last_atr_update = time.time()

    def calculate_quantity(self, stop_distance: float, risk_config: dict):
        """Calculate quantity based on risk % and stop distance"""
        final_qty = calc_quantity(stop_distance, risk_config)
        self.add_log(f"Calc Size: StopDist={stop_distance:.2f} -> Qty={final_qty}")
        return final_qty

    def get_capped_stop(self, entry_price: float, raw_stop: float, side: str = 'BUY'):
        """Apply ATR-based stop loss limit if configured"""
        max_stop_multiplier = self.risk_config.get('max_stop_atr', 0.0)
        
        capped_stop = calculate_capped_stop(entry_price, raw_stop, side, self.state.atr, max_stop_multiplier)
        
        if capped_stop != raw_stop:
            self.add_log(f"Stop Capped! Adjusted from {raw_stop:.2f} to {capped_stop:.2f}")
            
        return capped_stop

    @abstractmethod
    def on_ticker_update(self, last_price: float, ticker):
        """Real-time signal check"""
        pass

    @abstractmethod
    async def on_bar_update(self, bars, has_new_bar: bool):
        """Periodic bar updates (1min, 5min etc)"""
        # Periodic ATR Refresh (every 30 mins)
        if time.time() - self.last_atr_update > 1800:
            await self.update_atr()

    def add_log(self, message: str):
        self.state.add_log(message)
