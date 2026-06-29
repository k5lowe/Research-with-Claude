#!/usr/bin/env python3
"""
Day trading bot: EMA crossover (9/21) with RSI confirmation.
Trades US equities via Alpaca. See config.py and .env for setup.

WARNING: This places REAL orders when ALPACA_BASE_URL points to the live endpoint.
         Test thoroughly on paper trading first.
"""

import logging
import time
from datetime import datetime, date
from zoneinfo import ZoneInfo

import alpaca_trade_api as tradeapi
import pandas as pd

import config
from strategy import Signal, compute_signal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")


def get_api() -> tradeapi.REST:
    return tradeapi.REST(
        config.ALPACA_API_KEY,
        config.ALPACA_SECRET_KEY,
        config.ALPACA_BASE_URL,
        api_version="v2",
    )


def is_trading_window() -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:  # Saturday/Sunday
        return False
    start = now.replace(hour=config.MARKET_OPEN_HOUR, minute=config.MARKET_OPEN_MINUTE, second=0)
    end = now.replace(hour=config.MARKET_CLOSE_HOUR, minute=config.MARKET_CLOSE_MINUTE, second=0)
    return start <= now <= end


def get_account_equity(api: tradeapi.REST) -> float:
    account = api.get_account()
    return float(account.equity)


def get_daily_pnl(api: tradeapi.REST) -> float:
    account = api.get_account()
    return float(account.equity) - float(account.last_equity)


def get_bars(api: tradeapi.REST, symbol: str) -> pd.DataFrame:
    bars = api.get_bars(
        symbol,
        config.BAR_TIMEFRAME,
        limit=config.LOOKBACK_BARS,
    ).df
    if bars.empty:
        return bars
    bars = bars[["open", "high", "low", "close", "volume"]].copy()
    bars.index = pd.to_datetime(bars.index, utc=True)
    return bars.sort_index()


def calc_shares(equity: float, price: float) -> int:
    """Risk-based position size: risk RISK_PER_TRADE of equity, stop at STOP_LOSS_PCT."""
    risk_amount = equity * config.RISK_PER_TRADE
    risk_per_share = price * config.STOP_LOSS_PCT
    shares = int(risk_amount / risk_per_share)
    return max(shares, 1)


def has_position(api: tradeapi.REST, symbol: str) -> bool:
    try:
        pos = api.get_position(symbol)
        return int(pos.qty) != 0
    except tradeapi.rest.APIError:
        return False


def open_long(api: tradeapi.REST, symbol: str, price: float, equity: float) -> None:
    shares = calc_shares(equity, price)
    stop_price = round(price * (1 - config.STOP_LOSS_PCT), 2)
    take_profit_price = round(price * (1 + config.TAKE_PROFIT_PCT), 2)

    log.info(
        "BUY %s: qty=%d price=~%.2f stop=%.2f tp=%.2f",
        symbol, shares, price, stop_price, take_profit_price,
    )
    # Bracket order: entry + OCA stop-loss + take-profit
    api.submit_order(
        symbol=symbol,
        qty=shares,
        side="buy",
        type="market",
        time_in_force="day",
        order_class="bracket",
        stop_loss={"stop_price": stop_price},
        take_profit={"limit_price": take_profit_price},
    )


def close_position(api: tradeapi.REST, symbol: str) -> None:
    log.info("Closing position for %s", symbol)
    api.close_position(symbol)


def close_all_positions(api: tradeapi.REST) -> None:
    log.info("Closing all positions (end-of-day or max loss hit)")
    api.close_all_positions()


def check_max_daily_loss(api: tradeapi.REST, equity: float) -> bool:
    """Returns True if daily loss limit has been breached."""
    pnl = get_daily_pnl(api)
    threshold = -equity * config.MAX_DAILY_LOSS_PCT
    if pnl < threshold:
        log.warning("Max daily loss breached: P&L=%.2f threshold=%.2f", pnl, threshold)
        return True
    return False


def run() -> None:
    api = get_api()

    account = api.get_account()
    if account.trading_blocked:
        log.error("Account is blocked from trading. Exiting.")
        return

    log.info(
        "Starting trader | endpoint=%s | symbols=%s | equity=$%.2f",
        config.ALPACA_BASE_URL,
        config.SYMBOLS,
        float(account.equity),
    )

    halted = False
    last_signal_date: dict[str, date] = {}  # prevent re-entry on same signal day

    while True:
        try:
            if not is_trading_window():
                log.info("Outside trading window, waiting...")
                time.sleep(config.POLL_INTERVAL)
                continue

            equity = get_account_equity(api)

            if not halted and check_max_daily_loss(api, equity):
                close_all_positions(api)
                halted = True
                log.warning("Trading halted for the rest of the day.")

            if halted:
                time.sleep(config.POLL_INTERVAL)
                continue

            # Reset halt at start of new trading day
            today = datetime.now(ET).date()
            if getattr(run, "_last_halt_date", None) != today:
                halted = False
                run._last_halt_date = today

            for symbol in config.SYMBOLS:
                bars = get_bars(api, symbol)
                if bars.empty:
                    log.warning("No bars for %s, skipping", symbol)
                    continue

                signal = compute_signal(
                    bars,
                    config.EMA_SHORT,
                    config.EMA_LONG,
                    config.RSI_PERIOD,
                    config.RSI_OVERBOUGHT,
                    config.RSI_OVERSOLD,
                )
                price = bars["close"].iloc[-1]
                in_position = has_position(api, symbol)

                log.info("%s | signal=%s | price=%.2f | in_position=%s", symbol, signal.value, price, in_position)

                if signal == Signal.BUY and not in_position:
                    # Avoid re-entering on same day's signal
                    if last_signal_date.get(symbol) != today:
                        open_long(api, symbol, price, equity)
                        last_signal_date[symbol] = today

                elif signal == Signal.SELL and in_position:
                    close_position(api, symbol)

            # Close all positions 15 min before market close
            now = datetime.now(ET)
            eod_cutoff = now.replace(
                hour=config.MARKET_CLOSE_HOUR,
                minute=config.MARKET_CLOSE_MINUTE,
                second=0,
            )
            if now >= eod_cutoff:
                close_all_positions(api)
                log.info("End-of-day: all positions closed. Waiting for next session.")
                # Sleep until next day
                time.sleep(3600)
                continue

        except Exception as exc:
            log.exception("Unexpected error: %s", exc)

        time.sleep(config.POLL_INTERVAL)


if __name__ == "__main__":
    run()
