import yfinance as yf
import pandas as pd
import numpy as np

def get_real_iv_rank(ticker: str) -> float:
    """
    Uses yfinance to calculate a 1-year Historical Volatility Rank 
    to replace mocked IV data.
    """
    try:
        # Download 1 year of daily data quietly
        df = yf.download(ticker, period="1y", progress=False)
        if df.empty:
            return 50.0
            
        # Handle yfinance multi-index columns in newer versions
        close_prices = df['Close'].iloc[:, 0] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        
        # Calculate daily returns and 20-day rolling annualized volatility
        returns = close_prices.pct_change().dropna()
        rolling_vol = returns.rolling(window=20).std() * np.sqrt(252) * 100
        rolling_vol = rolling_vol.dropna()
        
        if rolling_vol.empty:
            return 50.0
            
        current_vol = float(rolling_vol.iloc[-1])
        min_vol = float(rolling_vol.min())
        max_vol = float(rolling_vol.max())
        
        if max_vol == min_vol:
            return 50.0
            
        iv_rank = ((current_vol - min_vol) / (max_vol - min_vol)) * 100
        return round(iv_rank, 2)
        
    except Exception as e:
        print(f"  [Debug] yfinance IV fallback for {ticker}: {e}")
        return 50.0