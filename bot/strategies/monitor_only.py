from bot.strategy import BaseStrategy
import logging

logger = logging.getLogger(__name__)

class MonitorOnlyStrategy(BaseStrategy):
    async def initialize(self):
        await super().initialize() # ATR calculation
        self.state.status = "OBSERVING"
        self.add_log(f"Started monitoring {self.symbol} (No execution)")

    def on_ticker_update(self, last_price: float, ticker):
        # Only observing, no entry logic
        pass

    async def on_bar_update(self, bars, has_new_bar: bool):
        await super().on_bar_update(bars, has_new_bar)
        # Extract basic info for the dashboard
        if not bars: return
        last_bar = bars[-1]
        self.state.last_price = last_bar.close
        # We don't set ORB levels here, but we could if needed for display
