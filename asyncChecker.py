import asyncio
from datetime import datetime, UTC
import pandas as pd
import test

from dataPrefix import (
    BINANCE_COLUMNS,
    get_all_contract_symbols,
    get_binance_klines_with_rate_limit,
    klines_to_dataframe,
)
from rule import (
    check_bullish_sma,
    detect_exploded_volume,
)
from messageSender import send_message_notify

# ============ Configuration ============
# Provide your tokens via environment variables for safety.
TELEGRAM_TOKEN =  "6519297911:AAH-cGmGvF6wh0Gb-55sBBhB0Hi8W6j3U0c"
TELEGRAM_CHAT_ID = "1188913547"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1242331878053253142/uK3gJYARjx_Js8zN0n5LZa7vXzSziQGDGxGVxyYX-QDMZUUbGXeQjHGi9zoD9OUTnhP6"  
    

# Symbols you don't want to track
DONT_TRACK_SYMBOLS = {"USDCUSDT", "BTCSTUSDT"}

# Periodic SMA checks (persisted across loops)
need_checked_4h = True
need_checked_1d = True

# Latest SMA trend cache results
last_sma_check_4h = {}
last_sma_check_1d = {}

# Cached raw 4H klines to avoid double-fetch in the same loop
cached_4h_data = {}

SMA_LENGTHS = [30, 45, 60]


async def process_symbol(session, symbol, check_15m, check_1h, check_4h_volume):
    """
    Fetches the data needed for each timeframe and applies the notification rule.
    Returns a message string if the symbol should be notified, else None.
    """
    try:
        exploded_timeframes = []

        # 15m
        if check_15m:
            data_15m = await get_binance_klines_with_rate_limit(session, symbol, "15m", 150)
            if isinstance(data_15m, list) and len(data_15m) > 0:
                df_15 = klines_to_dataframe(data_15m, BINANCE_COLUMNS)
                ok, pct = detect_exploded_volume(df_15, vol_len=45, multiplier=5)
                if ok:
                    exploded_timeframes.append(f"15m({pct})")

        # 1h
        if check_1h:
            data_1h = await get_binance_klines_with_rate_limit(session, symbol, "1h", 150)
            if isinstance(data_1h, list) and len(data_1h) > 0:
                df_1h = klines_to_dataframe(data_1h, BINANCE_COLUMNS)
                ok, pct = detect_exploded_volume(df_1h, vol_len=45, multiplier=5)
                if ok:
                    exploded_timeframes.append(f"1h({pct})")

        # 4h (volume only)
        if check_4h_volume:
            if symbol in cached_4h_data:
                data_4h = cached_4h_data[symbol]
            else:
                data_4h = await get_binance_klines_with_rate_limit(session, symbol, "4h", 150)
            if isinstance(data_4h, list) and len(data_4h) > 0:
                df_4h = klines_to_dataframe(data_4h, BINANCE_COLUMNS)
                ok, pct = detect_exploded_volume(df_4h, vol_len=45, multiplier=5)
                if ok:
                    exploded_timeframes.append(f"4h({pct})")

        # Trend annotation based on latest SMA checks
        trend_text = ""
        if exploded_timeframes:
            is_4h_bull = last_sma_check_4h.get(symbol, False)
            is_1d_bull = last_sma_check_1d.get(symbol, False)

            if is_4h_bull and is_1d_bull:
                trend_text = "，多頭排列: 4h + 1d"
            elif is_4h_bull:
                trend_text = "，多頭排列: 4h"
            elif is_1d_bull:
                trend_text = "，多頭排列: 1d"

            return f"{symbol} 爆量：{', '.join(exploded_timeframes)}{trend_text}"

        return None

    except Exception as e:
        print(f"[process_symbol] {symbol} error: {e}")
        return None


async def main():
    global need_checked_4h, need_checked_1d, last_sma_check_4h, last_sma_check_1d, cached_4h_data
   
    all_symbols = await get_all_contract_symbols()
    # Filter & keep only USDT pairs (exchangeInfo already filters by USDT in our util, but keep guard)
    symbols = [s for s in all_symbols if "USDT" in s and s not in DONT_TRACK_SYMBOLS]

    async with __import__("aiohttp").ClientSession() as session:
        while True:
            now = datetime.now(UTC)
            minute = now.minute
            hour = now.hour

            # When to trigger per-timeframe scans
            check_15m = (minute % 15 == 0)
            check_1h = (minute == 0)
            check_4h_volume = (minute == 0 and hour % 4 == 0)

            # Determine whether to recompute SMA trends
            check_sma_4h = need_checked_4h or (hour % 4 == 0 and minute == 0)
            check_sma_1d = need_checked_1d or (hour == 0 and minute == 0)

            cached_4h_data = {}
            if check_sma_4h:
                print("抓取 4H SMA 資訊")
                last_sma_check_4h = {}
                for symbol in symbols:
                    try:
                        raw = await get_binance_klines_with_rate_limit(session, symbol, "4h", 150)
                        cached_4h_data[symbol] = raw
                        df = klines_to_dataframe(raw, BINANCE_COLUMNS, ohlc_only=True)
                        last_sma_check_4h[symbol] = check_bullish_sma(df, SMA_LENGTHS)
                    except Exception as e:
                        print(f"[4h SMA] {symbol} error: {e}")
                need_checked_4h = False

            if check_sma_1d:
                print("抓取 1D SMA 資訊")
                last_sma_check_1d = {}
                for symbol in symbols:
                    try:
                        raw = await get_binance_klines_with_rate_limit(session, symbol, "1d", 150)
                        df = klines_to_dataframe(raw, BINANCE_COLUMNS, ohlc_only=True)
                        last_sma_check_1d[symbol] = check_bullish_sma(df, SMA_LENGTHS)
                    except Exception as e:
                        print(f"[1d SMA] {symbol} error: {e}")
                need_checked_1d = False

            if check_15m or check_1h or check_4h_volume:
                print(f"開始掃描市場 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                tasks = [
                    process_symbol(session, symbol, check_15m, check_1h, check_4h_volume)
                    for symbol in symbols
                ]
                results = await asyncio.gather(*tasks)
                messages = [m for m in results if m]
                if messages:
                    notify_text = "\\n".join(messages)
                    await send_message_notify(
                        notify_text,
                        TELEGRAM_CHAT_ID,
                        TELEGRAM_TOKEN,
                        DISCORD_WEBHOOK_URL,
                    )

            await asyncio.sleep(60)
            print("\\033[A%s %s" % ("重新比對時間: ", datetime.now().strftime("%Y_%m_%d %H:%M:%S")))

def test_run():
    test.test()

if __name__ == "__main__":
    #asyncio.run(main())
    test_run()
