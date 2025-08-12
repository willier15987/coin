import aiohttp
import asyncio
import pandas as pd
import ta

# Column layout for Binance futures klines
BINANCE_COLUMNS = [
    'timestamp', 'open', 'high', 'low', 'close', 'volume',
    'close_time', 'quote_asset_volume', 'number_of_trades',
    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
]


async def get_all_contract_symbols():
    """
    Get all futures symbols. We keep only those that include 'USDT' to match original behavior.
    """
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            return [s['symbol'] for s in data.get('symbols', []) if 'USDT' in s.get('symbol', '')]


async def get_binance_klines_with_rate_limit(symbol: str, interval: str, limit: int = 500):
    """
    Fetch klines with basic rate-limit awareness (using X-MBX-USED-WEIGHT-1M header)
    """
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            headers = response.headers
        try:
            used_weight = int(headers.get('X-MBX-USED-WEIGHT-1M', 0))
        except (TypeError, ValueError):
            used_weight = 0
        remaining_weight = 1200 - used_weight
        if remaining_weight < 10:
            print(f"{symbol}, Rate limit approaching. Sleeping 60s.")
            await asyncio.sleep(60)
        return await response.json()
    
    


def klines_to_dataframe(data, columns, ohlc_only: bool = False) -> pd.DataFrame:
    """
    Convert raw klines list to a typed pandas DataFrame.
    If ohlc_only=True, we keep only open/high/low/close to speed up SMA checks.
    """
    df = pd.DataFrame(data, columns=columns)
    if ohlc_only:
        df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].astype(float)
    else:
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def calculate_volume_sma(df, length):
    df[f'vol_sma_{length}'] = ta.trend.sma_indicator(df['volume'], window=length)
    return df

async def get_data_after_fix(symbol: str, interval: str):
    data = await get_binance_klines_with_rate_limit(symbol, interval, 150)
    datafram = pd.DataFrame(data, columns=BINANCE_COLUMNS)
    datafram[['open', 'high', 'low', 'close', 'volume']] = datafram[['open', 'high', 'low', 'close', 'volume']].astype(float)
    datafram['timestamp'] = pd.to_datetime(datafram['timestamp'], unit='ms')
    datafram = calculate_volume_sma(datafram, 45)