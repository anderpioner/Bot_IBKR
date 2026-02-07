from bot.strategy import BaseStrategy
from bot.models import ORBLevels
from ib_insync import MarketOrder, StopOrder
import logging

logger = logging.getLogger(__name__)

class ORB5MinStrategy(BaseStrategy):
    async def initialize(self):
        await super().initialize() # ATR(14) calculation
        # Fetch today's 5min bars
        bars = await self.ib.reqHistoricalDataAsync(
            self.contract, endDateTime='', durationStr='1 D',
            barSizeSetting='5 mins', whatToShow='TRADES', useRTH=True)
        
        if not bars:
            return

        # The first bar of the day (Retail Trading Hours)
        first_bar = bars[0]
        self.state.levels = ORBLevels(
            high=first_bar.high, 
            low=first_bar.low, 
            open=first_bar.open,
            close=first_bar.close,
            candle_time=first_bar.date.isoformat() if hasattr(first_bar.date, 'isoformat') else str(first_bar.date)
        )
        self.state.status = "MONITORING"
        self.add_log(f"ORB Levels set: High={self.state.levels.high}, Low={self.state.levels.low}")

    def on_ticker_update(self, last_price: float, ticker):
        if self.state.status == "MONITORING" and self.state.levels:
            if last_price > self.state.levels.high:
                self.execute_entry(last_price)

    async def on_bar_update(self, bars, has_new_bar: bool):
        await super().on_bar_update(bars, has_new_bar) # Handles ATR refresh

    def execute_entry(self, price: float):
        self.state.status = "IN_TRADE"
        self.state.entry_price = price
        raw_stop = self.state.levels.low
        self.state.stop_loss = self.get_capped_stop(price, raw_stop)
        
        stop_dist = abs(price - self.state.stop_loss)
        quantity = self.calculate_quantity(stop_dist, self.risk_config)
        
        parent = MarketOrder('BUY', quantity)
        stop_order = StopOrder('SELL', quantity, self.state.stop_loss)
        stop_order.parentId = parent.orderId
        stop_order.transmit = True
        
        self.ib.placeOrder(self.contract, parent)
        self.ib.placeOrder(self.contract, stop_order)
        
        self.add_log(f"Entry BUY at {price}. Stop Loss at {self.state.stop_loss}")
