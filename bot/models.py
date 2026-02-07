from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class ORBLevels:
    high: float
    low: float
    open: float = 0.0
    close: float = 0.0
    candle_time: str = "" # Store as ISO string for JSON

@dataclass
class TradeState:
    symbol: str
    levels: Optional[ORBLevels] = None
    position: int = 0
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    status: str = "WAITING_FOR_ORB" 
    atr: float = 0.0
    last_price: float = 0.0
    logs: list[str] = field(default_factory=list)

    def add_log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")

    def to_dict(self):
        import dataclasses
        return dataclasses.asdict(self)
