from typing import Dict, Any


class PaperExecution:
    def __init__(self):
        self.orders = []

    def send_order(self, ticker: str, qty: float, price: float, side: str = 'buy') -> Dict[str, Any]:
        order = {"ticker": ticker, "qty": qty, "price": price, "side": side}
        self.orders.append(order)
        return order
