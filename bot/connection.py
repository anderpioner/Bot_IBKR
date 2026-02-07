import asyncio
from ib_insync import IB, util
import logging

class IBConnection:
    def __init__(self, host='127.0.0.1', port=7497, client_id=1):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = None
        self.logger = logging.getLogger(__name__)

    async def connect(self):
        try:
            if not self.ib:
                self.ib = IB()
            self.logger.info(f"Connecting to IBKR at {self.host}:{self.port} (Client ID: {self.client_id})...")
            await self.ib.connectAsync(self.host, self.port, clientId=self.client_id)
            self.logger.info("Successfully connected to IBKR.")
            return True
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            return False

    def disconnect(self):
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()
            self.logger.info("Disconnected from IBKR.")

    def is_connected(self):
        return self.ib and self.ib.isConnected()
