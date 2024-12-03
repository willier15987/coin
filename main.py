import requests
import pandas as pd
import numpy as np
import ta
import time
import _thread
from datetime import datetime

import ta.trend

def get_all_contract_symbols():
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    response = requests.get(url)
    data = response.json()
    symbols = [symbol['symbol'] for symbol in data['symbols'] if 'USDT' in symbol['symbol']]
    return symbols

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

    #print(response.json)
    return response.json()

def calculate_sma(df, length):
    sma_name = f'sma_{length}'
    df[sma_name] = ta.trend.sma_indicator(df['close'], window=length)
    return df

def calculate_volume_sma(df, length):
    sma_name = f'vol_sma_{length}'
    df[sma_name] = ta.trend.sma_indicator(df['volume'],window=length)
    return df

def send_telegram_message(chat_id, message, token):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message
    }
    response = requests.post(url, data=data)
    return response

# 發送Discord訊息
def send_discord_message(webhook_url, message):
    data = {
        "content": message
    }
    response = requests.post(webhook_url, json=data)
    return response

def send_message_notify(message):

    telegram_token = "6519297911:AAH-cGmGvF6wh0Gb-55sBBhB0Hi8W6j3U0c"
    chat_id = "1188913547"
    discord_webhook_url = "https://discord.com/api/webhooks/1242331878053253142/uK3gJYARjx_Js8zN0n5LZa7vXzSziQGDGxGVxyYX-QDMZUUbGXeQjHGi9zoD9OUTnhP6"

    #tg
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message
    }
    response = requests.post(url, data=data)
    #ds
    data = {
        "content": message
    }
    response2 = requests.post(discord_webhook_url, json=data)


def check_and_notify(symbol , df_15, df_4h, id, token, discordUrl):
    sendable = True
    latest_data_4h = df_4h.iloc[-2]
    latest_data_15 = df_15.iloc[-2]
    sma_30 = latest_data_4h['sma_30']
    sma_60 = latest_data_4h['sma_60']
    sma_90 = latest_data_4h['sma_90']

    sma_30_15m = latest_data_15['sma_30']
    sma_45_15m = latest_data_15['sma_45']
    sma_60_15m = latest_data_15['sma_60']

    vol_sma_45 = latest_data_15['vol_sma_45']
    vol = float(latest_data_15['volume'])

    close = float(latest_data_15['close'])
    open = float(latest_data_15['open'])
    high = float(latest_data_15['high'])
    low = float(latest_data_15['low'])
    
    #message = "這是一條測試通知。"
    #print(symbol + ", close:" + str(close) + ", opne:" + str(open) + ", high:" + str(high) + ", low:" + str(low) + ", 30:" + str(sma_30) + ', 60:' + str(sma_60) + ', 90:' + str(sma_90))
    if vol > vol_sma_45 * 5:
        print(symbol +" 15m 爆量")
    else:
        sendable = False

    if sma_30 > sma_60 and sma_60 > sma_90:
        print(symbol + " 4h 多頭排列")        
    elif sma_30 < sma_60 and sma_60 < sma_90:
        print(symbol + " 4h 空頭排列")
        sendable = False

    if close < open and open - low > (open - close) * 5: 
            print(symbol + " 15m 插針, " + str(open - low) + ", " + str((open - close) * 5))
    else:
        sendable = False

    if sendable:
        print(symbol + " alert!!!")
        message = f"{symbol} : 15m 爆量、插針、4h 多頭"
        response_tg = send_telegram_message(id,message, token)
        response_dis = send_discord_message(discordUrl,message)


    if sma_30_15m > sma_45_15m and sma_45_15m > sma_60_15m:
        if close < open :
            if (close - low) * 2 > (open - low):
                message = f"{symbol} : 15m 多頭趨勢，紅插針"
                send_telegram_message(id,message, token)
        else :
            if (open - low) * 2 > (close - low):
                message = f"{symbol} : 15m 多頭趨勢，綠插針"
                send_telegram_message(id,message, token)

def get_bigger_alert(symbol, df_15):
        
    #市場突然出現劇烈波動 => 價差超過前15根平均
    start_num = 3
    div_num = 15
    last_prices = df_15.iloc[- start_num + div_num: - start_num]
    high_low_diff = last_prices['high'] - last_prices['low']
    avg = high_low_diff.mean()
    print(symbol + "平均波動:" + str(avg))
    current_price = df_15.iloc[-2]
    high_low = current_price['high'] - current_price['low']

    if high_low > avg * 4 :
        print(symbol + "出現大波動")

def calculate_atr_ema(symbol, df, period=12):
    """
    計算 ATR (Average True Range) 並使用 EMA 平滑
    :param df: 包含 high, low, close 的 DataFrame
    :param period: 計算 ATR 的窗口大小
    :return: DataFrame，新增 'TR', 'ATR', 和 'ATR_EMA' 欄位
    """
    # 計算真實範圍 (TR)
    df['previous_close'] = df['close'].shift(1)  # 上一根收盤價
    df['tr'] = df[['high', 'low']].apply(lambda x: x['high'] - x['low'], axis=1)
    df['tr'] = df.apply(
        lambda row: max(row['tr'], abs(row['high'] - row['previous_close']), abs(row['low'] - row['previous_close'])),
        axis=1
    )
    
    # 計算簡單 ATR
    df['atr'] = df['tr'].rolling(window=period).mean()
    
    # 計算 ATR 的 EMA
    alpha = 2 / (period + 1)  # 平滑係數
    df['atr_ema'] = df['tr'].ewm(span=period, adjust=False).mean()

    # 移除多餘欄位
    df.drop(columns=['previous_close'], inplace=True)
    current_price = df.iloc[-2]
    #print(symbol + "當前價格：" + str(current_price['open']) + ", atr: " + str(current_price['atr_ema'])) 
    message = ""

    if current_price['close'] > (current_price['open'] + float(current_price['atr_ema']) * 2):
        message = f"{symbol} : 大波動突破"
        print(symbol + "大波動突破")

    if current_price['close'] < (current_price['open'] - float(current_price['atr_ema']) * 2):
        message = f"{symbol} : 大波動跌破"
        
        print(symbol + "大波動跌破")

    if message != "":
        send_message_notify(message)

def check_sma_long(symbol , df_4h):
    pass_ = True
    latest_data_4h = df_4h.iloc[-2]
    sma_30 = latest_data_4h['sma_30']
    sma_60 = latest_data_4h['sma_60']
    sma_90 = latest_data_4h['sma_90']

    if sma_30 > sma_60 and sma_60 > sma_90:
        pass_ = True
        print(symbol + " 4h 多頭排列")        
    else:
        pass_ = False

    return pass_

def check_sma_short(symbol , df_4h):
    pass_ = True
    latest_data_4h = df_4h.iloc[-2]
    sma_30 = latest_data_4h['sma_30']
    sma_60 = latest_data_4h['sma_60']
    sma_90 = latest_data_4h['sma_90']

    if sma_30 < sma_60 and sma_60 < sma_90:
        pass_ = True
        print(symbol + " 4h 空頭排列")
    else:
        pass_ = False

    return pass_

def check_vol_kline(symbol , df_15, isLong):    
    pass_ = True

    latest_data_15 = df_15.iloc[-2]
    vol_sma_45 = latest_data_15['vol_sma_45']
    vol = float(latest_data_15['volume'])

    close = float(latest_data_15['close'])
    open = float(latest_data_15['open'])
    high = float(latest_data_15['high'])
    low = float(latest_data_15['low'])

    #if isLong:
    #    get_bigger_alert(symbol, df_15)

    if vol > vol_sma_45 * 5:
        pass_ = True
        #print(symbol +" 15m 爆量")
    else:
        pass_ = False

    if not pass_:
        return pass_

    if isLong:        
        if close < open and open - low > (open - close) * 2 and close - low > (high - open) * 3: 
            print(symbol + " 15m 爆量 紅插針, (多)")
        elif open < close and open - low > (close - open) * 2 and open - low > (high - close) * 3:
            print(symbol + " 15m 爆量 綠插針, (多)")
        else:
            pass_ = False
    else: 
        if close < open and high - close > (open - close) * 2 and high - open > (close - low) * 3: 
            print(symbol + " 15m 爆量 紅插針, (空)")
        elif open < close and high - open > (close - open) * 2 and high - close > (open - low) * 3:
            print(symbol + " 15m 爆量 綠插針, (空)")
        else:
            pass_ = False

    return pass_

def send_notify(message, id, token, discordUrl):
    print(message)
    #message = f"{symbol} : 15m 爆量、插針、4h 多頭"
    try:
        response_tg = send_telegram_message(id,message, token)
    except Exception as e:
        print(f"TG 機器人無法傳送{symbol}, 錯誤訊息：{e}")

    try:   
        response_dis = send_discord_message(discordUrl,message)
    except Exception as e:
        print(f"Discord 機器人無法傳送{symbol}, 錯誤訊息：{e}")

# 输入时间段
def get_input_time_period():
    start_date_str = input("请输入开始日期 (格式: YYYY-MM-DD): ")
    end_date_str = input("请输入结束日期 (格式: YYYY-MM-DD): ")
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    return start_date, end_date

def check_recentLow():
    print()

def Test(symbol):
    data_4h = get_binance_klines_with_rate_limit(symbol, '4h', 150)
    df_4h = pd.DataFrame(data_4h, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 
        'close_time', 'quote_asset_volume', 'number_of_trades', 
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])                
                
    df_4h = calculate_sma(df_4h, 30)
    df_4h = calculate_sma(df_4h, 60)
    df_4h = calculate_sma(df_4h, 90)
    one = True
    one = one and check_sma_long(symbol, df_4h)
    two = True
    two = two and check_sma_short(symbol, df_4h)
    print(one)
    print(two)

#main info
telegram_token = "6519297911:AAH-cGmGvF6wh0Gb-55sBBhB0Hi8W6j3U0c"
chat_id = "1188913547"
discord_webhook_url = "https://discord.com/api/webhooks/1242331878053253142/uK3gJYARjx_Js8zN0n5LZa7vXzSziQGDGxGVxyYX-QDMZUUbGXeQjHGi9zoD9OUTnhP6"
all_contract_symbols = get_all_contract_symbols()
#all_contract_symbols_better_main_coin = 
#print(f"所有合約幣種: {all_contract_symbols}")
#[0,5,10,15,20,25,30,35,40,45,50,55]:
print("開始執行...")
'''ans_1 = input("是否檢查最近漲跌？(y/n)")
if ans_1 == "Y" or ans_1 == "y":
    check_recentLow()

else:
    print("開始重複執行K線提醒...")'''
#Test('TNSRUSDT')
dontTrackSymbol = ["USDCUSDT", "BTCSTUSDT"]
while True:
    current_minute = datetime.now().minute
    if current_minute in [0,15,30,45]:
        print("開始搜尋, " + datetime.now().strftime('%Y_%m_%d %H:%M:%S'))
        for symbol in all_contract_symbols:
            if symbol in dontTrackSymbol:
                continue
            try:
                #插針與爆量
                data = get_binance_klines_with_rate_limit(symbol, '15m', 150)
                df_15 = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume', 
                    'close_time', 'quote_asset_volume', 'number_of_trades', 
                    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                ])

                df_15['high'] = df_15['high'].astype(float)
                df_15['low'] = df_15['low'].astype(float)
                df_15['close'] = df_15['close'].astype(float)
                df_15['open'] = df_15['open'].astype(float)

                df_15['timestamp'] = pd.to_datetime(df_15['timestamp'], unit='ms')

                calculate_atr_ema(symbol, df_15)

                df_15 = calculate_volume_sma(df_15, 45)
                df_15 = calculate_sma(df_15, 30)
                df_15 = calculate_sma(df_15, 45)
                df_15 = calculate_sma(df_15, 60)

                send_long =  check_vol_kline(symbol, df_15, True)
                send_short =  check_vol_kline(symbol, df_15, False)

                #均線
                if send_long or send_short:
                    data_4h = get_binance_klines_with_rate_limit(symbol, '4h', 150)
                    df_4h = pd.DataFrame(data_4h, columns=[
                        'timestamp', 'open', 'high', 'low', 'close', 'volume', 
                        'close_time', 'quote_asset_volume', 'number_of_trades', 
                        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                    ])                
                
                    df_4h = calculate_sma(df_4h, 30)
                    df_4h = calculate_sma(df_4h, 60)
                    df_4h = calculate_sma(df_4h, 90)

                    if send_long:
                        send_long = send_long and check_sma_long(symbol, df_4h)
                    elif send_short:
                        send_short = send_short and check_sma_short(symbol, df_4h)
                    else:
                        print("壞去惹 QQ")
                    
                    if send_long:
                        send_notify(f"{symbol} : 15m 爆量、插針、4h 多頭 (做多摟！)", chat_id, telegram_token, discord_webhook_url)
                    if send_short:
                        send_notify(f"{symbol} : 15m 爆量、插針、4h 空頭 (做空瞜！)", chat_id, telegram_token, discord_webhook_url)
                #check_and_notify(symbol ,df_15, df_4h, chat_id, telegram_token, discord_webhook_url)  
            except Exception as e:
                print(f"Error processing {symbol}: {e}")        
        print("一輪結束, 時間：" + datetime.now().strftime('%Y_%m_%d %H:%M:%S'))
        print("\n")
        time.sleep(60) #結束後延長一分鐘才繼續檢查，避免同一分鐘檢查太多次
    else:
        time.sleep(15)
        print('\033[A%s %s' % ("重新比對時間: ",datetime.now().strftime('%Y_%m_%d %H:%M:%S')))
