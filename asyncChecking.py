import aiohttp  # [改動] 改用 aiohttp 進行非同步 HTTP 請求
import asyncio
import pandas as pd
import ta
import time
from datetime import datetime, UTC

import ta.trend

# 儲存最近一次的 SMA 多頭排列結果（symbol 對應 True/False）
last_sma_check_4h = {}
last_sma_check_1d = {}

# 紀錄上次檢查時間
need_checked_4h = True
need_checked_1d = True

BINANCE_COLUMNS = [
    'timestamp', 'open', 'high', 'low', 'close', 'volume',
    'close_time', 'quote_asset_volume', 'number_of_trades',
    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ]

# 獲取所有合約交易對
async def get_all_contract_symbols():
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            return [symbol['symbol'] for symbol in data['symbols'] if 'USDT' in symbol['symbol']]

# 非同步獲取 Binance K 線數據
async def get_binance_klines_with_rate_limit(symbol, interval, limit=500):
    url = f"https://fapi.binance.com/fapi/v1/klines"
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            headers = response.headers
            used_weight = int(headers.get('X-MBX-USED-WEIGHT-1M', 0))
            remaining_weight = 1200 - used_weight

            if remaining_weight < 10:  # [改動] 根據剩餘 API 速率動態等待
                print(f"{symbol}, Rate limit reached. Waiting for reset.")
                await asyncio.sleep(60)  

            return await response.json()

# 非同步發送 Telegram 訊息
async def send_telegram_message(chat_id, message, token):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": message}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data) as response:
            return await response.json()

# 非同步發送 Discord 訊息
async def send_discord_message(webhook_url, message, max_retries=3):
    data = {"content": message}
    retries = 0
    
    async with aiohttp.ClientSession() as session:
            try:
                async with session.post(webhook_url, json=data) as response:
                    if response.status == 204:
                        return True  # Discord webhook 無內容成功
                    elif response.status == 429:
                        # Discord Rate Limit
                        retry_after = float(response.headers.get("Retry-After", 5))
                        print(f"[Rate Limit] Waiting for {retry_after} seconds...")
                        retries += 1
                    elif response.status >= 400:
                        text = await response.text()
                        print(f"[Discord Error] Status {response.status}: {text}")
                        return False
                    else:
                        try:
                            return await response.json()
                        except aiohttp.ContentTypeError:
                            return True  # 成功但無 json 回傳
            except aiohttp.ClientError as e:
                print(f"[Discord Network Error] {e}")
                await asyncio.sleep(2)
                retries += 1
    print(f"[Discord Error] Failed after {max_retries} retries.")
    return False

# 異步通知
async def send_message_notify(message, chat_id, telegram_token, discord_webhook_url):
    await asyncio.gather(
        send_telegram_message(chat_id, message, telegram_token),
        send_discord_message(discord_webhook_url, message)
    )

# 計算均線 (SMA)
def calculate_sma(df, length):
    df[f'sma_{length}'] = ta.trend.sma_indicator(df['close'], window=length)
    return df

# 計算成交量均線
def calculate_volume_sma(df, length):
    df[f'vol_sma_{length}'] = ta.trend.sma_indicator(df['volume'], window=length)
    return df

def check_sma(df, lengths):
    """
    傳入 SMA 週期 list（例如 [30, 45, 60]），回傳是否為多頭排列
    多頭排列定義為：短期 > 中期 > 長期（由小排到大）
    """
    sorted_lengths = sorted(lengths)  # 由短到長排序
    for length in sorted_lengths:
        df = calculate_sma(df, length)

    # 取出最後一根 K 線的對應 sma 值
    last_values = [df[f'sma_{l}'].iloc[-2] for l in sorted_lengths]

    # 檢查是否為遞減（短期 > 長期）
    return all(x > y for x, y in zip(last_values, last_values[1:]))

async def process_symbol(symbol, check_15m, check_1h, check_4h, current_4h_trend, current_1d_trend, cached_4h_data, chat_id, telegram_token, discord_webhook_url):
    try:
        exploded_timeframes = []  # 用來儲存爆量的週期

        # --- 15m ---
        if check_15m:
            data_15m = await get_binance_klines_with_rate_limit(symbol, '15m', 150)
            df_15 = pd.DataFrame(data_15m, columns=BINANCE_COLUMNS)
            df_15[['open', 'high', 'low', 'close', 'volume']] = df_15[['open', 'high', 'low', 'close', 'volume']].astype(float)
            df_15['timestamp'] = pd.to_datetime(df_15['timestamp'], unit='ms')
            df_15 = calculate_volume_sma(df_15, 45)

            if df_15['volume'].iloc[-2] > df_15['vol_sma_45'].iloc[-2] * 5:
                volue = "{:.1%}".format((df_15['close'].iloc[-2] - df_15['open'].iloc[-2]) / df_15['open'].iloc[-2])
                exploded_timeframes.append(f"15m({volue})")

        # --- 1h ---
        if check_1h:
            data_1h = await get_binance_klines_with_rate_limit(symbol, '1h', 150)
            df_1h = pd.DataFrame(data_1h, columns=BINANCE_COLUMNS)
            df_1h[['open', 'high', 'low', 'close', 'volume']] = df_1h[['open', 'high', 'low', 'close', 'volume']].astype(float)
            df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'], unit='ms')
            df_1h = calculate_volume_sma(df_1h, 45)

            if df_1h['volume'].iloc[-2] > df_1h['vol_sma_45'].iloc[-2] * 5:
                volue = "{:.1%}".format((df_1h['close'].iloc[-2] - df_1h['open'].iloc[-2]) / df_1h['open'].iloc[-2])
                exploded_timeframes.append(f"1h({volue})")

        # --- 4h ---
        if check_4h:
            if symbol in cached_4h_data:
                data_4h = cached_4h_data[symbol]
            else:
                data_4h = await get_binance_klines_with_rate_limit(symbol, '4h', 150)
            df_4h = pd.DataFrame(data_4h, columns=BINANCE_COLUMNS)
            df_4h[['open', 'high', 'low', 'close', 'volume']] = df_4h[['open', 'high', 'low', 'close', 'volume']].astype(float)
            df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'], unit='ms')
            df_4h = calculate_volume_sma(df_4h, 45)

            if df_4h['volume'].iloc[-2] > df_4h['vol_sma_45'].iloc[-2] * 5:
                volue = "{:.1%}".format((df_4h['close'].iloc[-2] - df_4h['open'].iloc[-2]) / df_4h['open'].iloc[-2])
                exploded_timeframes.append(f"4h({volue})")

        # ✅ SMA 多頭判斷結果納入條件
        trend_text = ""
        if exploded_timeframes and current_4h_trend.get(symbol, False) and current_1d_trend.get(symbol, False):
            trend_text = "，多頭排列: 4h + 1d"
        elif exploded_timeframes and current_4h_trend.get(symbol, False):
            trend_text = "，多頭排列: 4h"
        elif exploded_timeframes and current_1d_trend.get(symbol, False):
            trend_text = "，多頭排列: 1d"
        elif exploded_timeframes:
            trend_text = ""

        # 發送通知
        if exploded_timeframes:
            message = f"{symbol} 爆量：{', '.join(exploded_timeframes)}{trend_text}"
            await send_message_notify(message, chat_id, telegram_token, discord_webhook_url)

    except Exception as e:
        print(f"Error processing {symbol}: {e}")

# 主函數，每 15 分鐘執行一次
async def main():
    global need_checked_4h, need_checked_1d
    telegram_token = "6519297911:AAH-cGmGvF6wh0Gb-55sBBhB0Hi8W6j3U0c"
    chat_id = "1188913547"
    discord_webhook_url = "https://discord.com/api/webhooks/1242331878053253142/uK3gJYARjx_Js8zN0n5LZa7vXzSziQGDGxGVxyYX-QDMZUUbGXeQjHGi9zoD9OUTnhP6"  
    all_contract_symbols = await get_all_contract_symbols()
    dontTrackSymbol = ["USDCUSDT", "BTCSTUSDT"]

    sma_lengths = [30, 45, 60]

    while True:
        now = datetime.now(UTC)
        #noww = datetime.utcnow()
        minute = now.minute
        hour = now.hour

        check_15m = (minute % 15 == 0)
        check_1h = (minute == 0)
        check_4h_volume = (minute == 0 and hour % 4 == 0)

        if need_checked_4h:
            check_sma_4h = True
        elif now.hour % 4 == 0 and now.minute == 0:
            check_sma_4h = True
        else:
            check_sma_4h = False

        if need_checked_1d:
            check_sma_1d = True
        elif now.hour == 0 and now.minute == 0:
            check_sma_1d = True
        else:
            check_sma_1d = False
        #check_sma_4h = need_checked_4h or now.hour % 4 == 0 and now.minute == 0)
        #check_sma_1d = (need_checked_1d or now.hour == 0 and now.minute == 0)
        cached_4h_data = {}
        # 若是到時間則重新計算 trend 結果
        if check_sma_4h:
            print("抓取 4H sma 資訊")
            last_sma_check_4h = {}
            cached_4h_data = {}
            for symbol in all_contract_symbols:
                if symbol in dontTrackSymbol: continue
                try:
                    data = await get_binance_klines_with_rate_limit(symbol, '4h', 150)
                    cached_4h_data[symbol] = data
                    df = pd.DataFrame(data, columns=BINANCE_COLUMNS)
                    df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].astype(float)
                    last_sma_check_4h[symbol] = check_sma(df, sma_lengths) #df['sma_30'].iloc[-2] > df['sma_60'].iloc[-2] > df['sma_90'].iloc[-2]
                except Exception as e:
                    print(f"4h SMA error for {symbol}: {e}")
            need_checked_4h = False

        if check_sma_1d:
            print("抓取 1d sma 資訊")
            last_sma_check_1d = {}
            for symbol in all_contract_symbols:
                if symbol in dontTrackSymbol: continue
                try:
                    data = await get_binance_klines_with_rate_limit(symbol, '1d', 150)
                    df = pd.DataFrame(data, columns=BINANCE_COLUMNS)
                    df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].astype(float)
                    last_sma_check_1d[symbol] = check_sma(df, sma_lengths)
                except Exception as e:
                    print(f"1d SMA error for {symbol}: {e}")
            need_checked_1d = False

        if check_15m or check_1h or check_4h_volume:
            print(f"開始掃描市場 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} \n")
            tasks = [
                process_symbol(
                    symbol,
                    check_15m,
                    check_1h,
                    check_4h_volume,
                    last_sma_check_4h,
                    last_sma_check_1d,
                    cached_4h_data,
                    chat_id,
                    telegram_token,
                    discord_webhook_url
                )
                for symbol in all_contract_symbols if symbol not in dontTrackSymbol
            ]
            await asyncio.gather(*tasks)

        await asyncio.sleep(60)  # [改動] 避免頻繁檢查
        
        print('\033[A%s %s' % ("重新比對時間: ",datetime.now().strftime('%Y_%m_%d %H:%M:%S')))

# 啟動異步執行
asyncio.run(main())
