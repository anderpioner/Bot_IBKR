from bot.strategy import BaseStrategy
from ib_insync import MarketOrder, StopOrder
import logging

logger = logging.getLogger(__name__)

class VWAP1MinStrategy(BaseStrategy):
    def __init__(self, ib, state, risk_config):
        super().__init__(ib, state, risk_config)
        self.vwap_sum_pv = 0.0
        self.vwap_sum_vol = 0
        self.vwap = 0.0
        self.signal_candle_high = None
        self.signal_candle_low = None

    async def initialize(self):
        await super().initialize() # ATR(14)
        # Fetch today's 1min bars to catch up with VWAP
        bars = await self.ib.reqHistoricalDataAsync(
            self.contract, endDateTime='', durationStr='1 D',
            barSizeSetting='1 min', whatToShow='TRADES', useRTH=True)
        
        if bars:
            await self.on_bar_update(bars, has_new_bar=False)
            self.add_log(f"Initialized VWAP: {self.vwap:.2f} using {len(bars)} previous bars.")
        
        self.state.status = "MONITORING" if self.state.status == "WAITING_FOR_ORB" else self.state.status

    def on_ticker_update(self, last_price: float, ticker):
        if self.state.status == "MONITORING" and self.signal_candle_high:
            if last_price > self.signal_candle_high:
                self.execute_entry(last_price)

    async def on_bar_update(self, bars, has_new_bar: bool):
        await super().on_bar_update(bars, has_new_bar)
        if not bars: return

        # Recalculate daily VWAP
        self.vwap_sum_pv = 0.0
        self.vwap_sum_vol = 0
        
        for bar in bars:
            self.vwap_sum_pv += bar.average * bar.volume
            self.vwap_sum_vol += bar.volume
        
        if self.vwap_sum_vol > 0:
            self.vwap = self.vwap_sum_pv / self.vwap_sum_vol

        # Check for signal: Close above VWAP
        last_bar = bars[-1]
        if self.state.status == "MONITORING" and not self.signal_candle_high:
            if last_bar.close > self.vwap:
                self.signal_candle_high = last_bar.high
                self.signal_candle_low = last_bar.low
                self.add_log(f"Signal Candle Found! Close ({last_bar.close:.2f}) > VWAP ({self.vwap:.2f}). Monitoring high: {self.signal_candle_high}")

    def execute_entry(self, price: float):
        self.state.status = "IN_TRADE"
        self.state.entry_price = price
        raw_stop = self.signal_candle_low # Stop at low of signal candle
        self.state.stop_loss = self.get_capped_stop(price, raw_stop)
        
        stop_dist = abs(price - self.state.stop_loss)
        quantity = self.calculate_quantity(stop_dist, self.risk_config)
        
        parent = MarketOrder('BUY', quantity)
        stop_order = StopOrder('SELL', quantity, self.state.stop_loss)
        stop_order.parentId = parent.orderId
        stop_order.transmit = True
        
        self.ib.placeOrder(self.contract, parent)
        self.ib.placeOrder(self.contract, stop_order)
        
        self.add_log(f"VWAP Breakout Entry at {price}. Stop Loss at {self.state.stop_loss}")
