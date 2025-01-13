import pandas as pd
import time
import requests
import ta

def get_all_contract_symbols():
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    response = requests.get(url)
    data = response.json()
    symbols = [symbol['symbol'] for symbol in data['symbols'] if 'USDT' in symbol['symbol']]
    return symbols

def calculate_sma(df, length):
    sma_name = f'sma_{length}'
    df[sma_name] = ta.trend.sma_indicator(df['close'], window=length)
    return df

def get_binance_klines_with_rate_limit(symbol, interval, limit=500):
    url = f"https://fapi.binance.com/fapi/v1/klines"
    params = {
        'symbol': symbol,
        'interval': interval,
        'limit': limit
    }
    response = requests.get(url, params=params)
    headers = response.headers
    
    # 獲取速率限制信息
    used_weight = int(headers.get('X-MBX-USED-WEIGHT-1M', 0))
    remaining_weight = 1200 - used_weight

    # 如果剩餘權重不足，則等待直到重置
    if remaining_weight < 10:  # 預留一些空間
        print(f"Rate limit reached. Waiting for reset.")
        time.sleep(60)  # 等待60秒直到重置

    return response.json()

def data_transform(symbol, timeframe):
    #print("執行單個時區")
    data = get_binance_klines_with_rate_limit(symbol, timeframe, 150)
    df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 
            'close_time', 'quote_asset_volume', 'number_of_trades', 
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['close'] = df['close'].astype(float)  # 確保 close 欄位是浮點數型別

        # 計算均線
    df = calculate_sma(df, ma_short)
    df = calculate_sma(df, ma_medium)
    df = calculate_sma(df, ma_long)

        # 檢查均線規則
    if (df[f'sma_{ma_short}'].iloc[-1] > df[f'sma_{ma_medium}'].iloc[-1] > df[f'sma_{ma_long}'].iloc[-1]):
        selected_symbols.append(symbol)

def data_transform_2(symbol, timeframe, timeframe_2):
    #print("執行兩個時區")
    data = get_binance_klines_with_rate_limit(symbol, timeframe, 150)
    df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 
            'close_time', 'quote_asset_volume', 'number_of_trades', 
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['close'] = df['close'].astype(float)  # 確保 close 欄位是浮點數型別

        # 計算均線
    df = calculate_sma(df, ma_short)
    df = calculate_sma(df, ma_medium)
    df = calculate_sma(df, ma_long)

    data2 = get_binance_klines_with_rate_limit(symbol, timeframe_2, 150)
    df2 = pd.DataFrame(data2, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 
            'close_time', 'quote_asset_volume', 'number_of_trades', 
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    df2['timestamp'] = pd.to_datetime(df2['timestamp'], unit='ms')
    df2['close'] = df2['close'].astype(float)  # 確保 close 欄位是浮點數型別

        # 計算均線
    df2 = calculate_sma(df2, ma_short)
    df2 = calculate_sma(df2, ma_medium)
    df2 = calculate_sma(df2, ma_long)

        # 檢查均線規則
    passMa1 = False
    passMa2 = False
    if (df[f'sma_{ma_short}'].iloc[-1] > df[f'sma_{ma_medium}'].iloc[-1] > df[f'sma_{ma_long}'].iloc[-1]):
        #print(symbol + "通過第一時區檢測")
        passMa1 = True
    
    if (passMa1 and df2[f'sma_{ma_short}'].iloc[-1] > df2[f'sma_{ma_medium}'].iloc[-1] > df2[f'sma_{ma_long}'].iloc[-1]):
        #print(symbol + "通過第二時區檢測")
        selected_symbols.append(symbol)
        passMa2 = True
   
    if passMa1 and not passMa2:
        print(symbol + "未通過第二時區檢測")

# 輸入參數並轉換為整數
all_contract_symbols = get_all_contract_symbols()
timeframe = input('輸入時間')  # 1小時K線
next_time_frame = input('第二個時間')
ma_short = int(input('最短周期'))
ma_medium = int(input('中周期'))
ma_long = int(input('最長周期'))

dontTrackSymbol = ["USDCUSDT", "BTCSTUSDT"]
selected_symbols = []

for symbol in all_contract_symbols:
    if symbol in dontTrackSymbol:
        continue

    if next_time_frame == "0":
        data_transform(symbol, timeframe)
    else :
        data_transform_2(symbol, timeframe, next_time_frame)
    '''data = get_binance_klines_with_rate_limit(symbol, timeframe, 150)
    df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 
            'close_time', 'quote_asset_volume', 'number_of_trades', 
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['close'] = df['close'].astype(float)  # 確保 close 欄位是浮點數型別

        # 計算均線
    df = calculate_sma(df, ma_short)
    df = calculate_sma(df, ma_medium)
    df = calculate_sma(df, ma_long)

        # 檢查均線規則
    if (df[f'sma_{ma_short}'].iloc[-1] > df[f'sma_{ma_medium}'].iloc[-1] > df[f'sma_{ma_long}'].iloc[-1]):
        selected_symbols.append(symbol)
    else:
        print(symbol + "不符合")'''

print("總共" + str(len(selected_symbols)))
for s in selected_symbols:
    print(s + "符合條件")
