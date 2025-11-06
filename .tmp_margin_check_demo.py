from providers.schwab_trading import SchwabTrader
from providers.schwab_mock import MockSchwabClient

trader = SchwabTrader(account_id="HASH_TEST", dry_run=False, client=MockSchwabClient(), export_dir="./trade_orders_test")
order = trader.create_cash_secured_put_order(
    symbol="AAPL", expiration="2025-12-19", strike=100.0, quantity=1, limit_price=1.50, duration="GTC"
)
prev = trader.preview_order(order)
mc = prev.get('margin_check')
print('status', prev.get('status'))
print('has_mc', isinstance(mc, dict))
print('mc', mc)
