import pandas as pd
import ta

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