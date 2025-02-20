import aiohttp  # [改動] 改用 aiohttp 進行非同步 HTTP 請求
import asyncio
import pandas as pd
import ta
import time
from datetime import datetime

import ta.trend

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
                print(f"Rate limit reached. Waiting for reset.")
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
async def send_discord_message(webhook_url, message):
    data = {"content": message}
    async with aiohttp.ClientSession() as session:
        async with session.post(webhook_url, json=data) as response:
            return await response.json()

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

# 處理單一交易對
async def process_symbol(symbol, chat_id, telegram_token, discord_webhook_url):
    try:
        data_15m = await get_binance_klines_with_rate_limit(symbol, '15m', 150)
        df_15 = pd.DataFrame(data_15m, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 
            'close_time', 'quote_asset_volume', 'number_of_trades', 
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        # 轉換數據格式
        df_15[['open', 'high', 'low', 'close', 'volume']] = df_15[['open', 'high', 'low', 'close', 'volume']].astype(float)
        df_15['timestamp'] = pd.to_datetime(df_15['timestamp'], unit='ms')

        # 計算技術指標
        df_15 = calculate_volume_sma(df_15, 45)
        df_15 = calculate_sma(df_15, 30)
        df_15 = calculate_sma(df_15, 45)
        df_15 = calculate_sma(df_15, 60)

        # 取得 4H K 線
        data_4h = await get_binance_klines_with_rate_limit(symbol, '4h', 150)
        df_4h = pd.DataFrame(data_4h, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 
            'close_time', 'quote_asset_volume', 'number_of_trades', 
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        df_4h[['open', 'high', 'low', 'close', 'volume']] = df_4h[['open', 'high', 'low', 'close', 'volume']].astype(float)
        df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'], unit='ms')

        df_4h = calculate_sma(df_4h, 30)
        df_4h = calculate_sma(df_4h, 60)
        df_4h = calculate_sma(df_4h, 90)

        # 判斷是否符合交易條件
        if df_15['volume'].iloc[-2] > df_15['vol_sma_45'].iloc[-2] * 5:
            if df_4h['sma_30'].iloc[-2] > df_4h['sma_60'].iloc[-2] and df_4h['sma_60'].iloc[-2] > df_4h['sma_90'].iloc[-2]:
                message = f"{symbol} : 15m 爆量、4h 多頭 (做多!)"
                await send_message_notify(message, chat_id, telegram_token, discord_webhook_url)

    except Exception as e:
        print(f"Error processing {symbol}: {e}")

# 主函數，每 15 分鐘執行一次
async def main():
    
    telegram_token = "6519297911:AAH-cGmGvF6wh0Gb-55sBBhB0Hi8W6j3U0c"
    chat_id = "1188913547"
    discord_webhook_url = "https://discord.com/api/webhooks/1242331878053253142/uK3gJYARjx_Js8zN0n5LZa7vXzSziQGDGxGVxyYX-QDMZUUbGXeQjHGi9zoD9OUTnhP6"  
    all_contract_symbols = await get_all_contract_symbols()
    dontTrackSymbol = ["USDCUSDT", "BTCSTUSDT"]

    while True:
        current_minute = datetime.now().minute
        if current_minute % 15 == 0:  # 每 15 分鐘運行一次
            print("開始掃描市場", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            
            tasks = [
                process_symbol(symbol, chat_id, telegram_token, discord_webhook_url)
                for symbol in all_contract_symbols if symbol not in dontTrackSymbol
            ]

            await asyncio.gather(*tasks)  # [改動] 並行處理所有交易對

        await asyncio.sleep(60)  # [改動] 避免頻繁檢查

# 啟動異步執行
asyncio.run(main())
