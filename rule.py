import pandas as pd
from ta.trend import sma_indicator

def _ensure_sma_columns(df: pd.DataFrame, lengths, source_col: str = 'close'):
    for l in lengths:
        col = f'sma_{l}'
        if col not in df.columns:
            df[col] = sma_indicator(df[source_col], window=l)


def check_bullish_sma(df: pd.DataFrame, lengths) -> bool:
    """
    多頭排列定義：短期 > 中期 > 長期（使用倒數第二根 K 線作判斷）
    Returns True if bullish alignment holds.
    """
    sorted_lengths = sorted(lengths)
    _ensure_sma_columns(df, sorted_lengths, 'close')
    last_vals = [df[f'sma_{l}'].iloc[-2] for l in sorted_lengths]
    # Strictly decreasing sequence of SMA values from short to long means price > short > mid > long
    return all(x > y for x, y in zip(last_vals, last_vals[1:]))


def detect_exploded_volume(df: pd.DataFrame, vol_len: int = 45, multiplier: float = 5.0):
    """
    檢查倒數第二根是否爆量: volume[-2] > SMA(volume, vol_len)[-2] * multiplier
    回傳 (True/False, 百分比文字或 '')
    百分比以 (close-open)/open 計算，格式如 '3.2%'
    """
    vol_sma_col = f'vol_sma_{vol_len}'
    if vol_sma_col not in df.columns:
        df[vol_sma_col] = sma_indicator(df['volume'], window=vol_len)

    if len(df) < 3:  # need at least 2 bars plus SMA warmup
        return False, ''

    # Use the last completed candle
    last_idx = -2

    try:
        is_exploded = df['volume'].iloc[last_idx] > df[vol_sma_col].iloc[last_idx] * multiplier
    except Exception:
        return False, ''

    if not is_exploded:
        return False, ''

    try:
        pct = (df['close'].iloc[last_idx] - df['open'].iloc[last_idx]) / df['open'].iloc[last_idx]
        pct_txt = "{:.1%}".format(pct)
    except Exception:
        pct_txt = ''
    return True, pct_txt
