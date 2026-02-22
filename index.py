import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
from datetime import datetime
import os
import ccxt
import pandas as pd
import numpy as np
import ta
import webbrowser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import matplotlib.pyplot as plt
from matplotlib import style
from matplotlib.patches import Rectangle
import matplotlib.dates as mdates
import requests
from PIL import ImageGrab
import pygetwindow as gw
import re
from colorama import init, Fore, Style
import queue

# Initialize colorama
init(autoreset=True)

# ============================================
# TELEGRAM BOT CONFIGURATION
# ============================================
TELEGRAM_BOT_TOKEN = "Replace with your bot token"  
TELEGRAM_CHANNEL_ID = "# Replace with your channel ID/username" 

# ============================================
# BOT 1: Candle Color Divergence Bot (FUTURES)
# ============================================
class CandleColorDivergenceBot:
    def __init__(self, timeframe='1m', rsi_period=14):
        # Use Futures API for Binance
        self.binance_exchange = ccxt.binance({
            'enableRateLimit': True,
            'timeout': 30000,
            'options': {
                'defaultType': 'future'  # THIS MAKES IT FUTURES
            }
        })
        self.timeframe = timeframe
        self.rsi_period = rsi_period
        self.long_signals = []
        self.short_signals = []
        
    def fetch_candles(self, symbol):
        try:
            # Ensure symbol is in correct format for futures
            if not symbol.endswith('USDT'):
                symbol = symbol + 'USDT'
            
            candles = self.binance_exchange.fetch_ohlcv(
                symbol, 
                timeframe=self.timeframe, 
                limit=40  # Keep 40 for calculation
            )
            if candles:
                df = pd.DataFrame(candles, 
                                 columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                
                if len(df) > self.rsi_period:
                    df['rsi'] = ta.momentum.RSIIndicator(
                        df['close'], 
                        window=self.rsi_period
                    ).rsi()
                else:
                    df['rsi'] = 50
                
                df['is_green'] = df['close'] > df['open']
                df['is_red'] = df['close'] < df['open']
                
                return df
        except Exception as e:
            return None
        return None
    
    def count_green_candles_between(self, df, start_idx, end_idx):
        count = 0
        start = min(start_idx, end_idx)
        end = max(start_idx, end_idx)
        for i in range(start + 1, end):
            if i < len(df) and df['is_green'].iloc[i]:
                count += 1
        return count
    
    def count_red_candles_between(self, df, start_idx, end_idx):
        count = 0
        start = min(start_idx, end_idx)
        end = max(start_idx, end_idx)
        for i in range(start + 1, end):
            if i < len(df) and df['is_red'].iloc[i]:
                count += 1
        return count
    
    def find_short_signals(self, df, symbol):
        """PURIFIED SHORT SIGNAL - GREEN CANDLES (Bearish Divergence)
           RULE: Peak2 RSI must be <= Peak1 RSI (RSI falling while price rising)"""
        if df is None or len(df) < 30:
            return []
        
        recent = df.tail(30).reset_index(drop=True)
        original_indices = df.tail(30).index
        
        # Step 1: Find green candles with their RSI after closing
        green_candles = []
        for i, orig_idx in zip(range(len(recent)), original_indices):
            if recent['is_green'].iloc[i] and not pd.isna(recent['rsi'].iloc[i]):
                green_candles.append({
                    'index': orig_idx,
                    'timestamp': recent['timestamp'].iloc[i],
                    'price': recent['high'].iloc[i],  # Use high for green candles
                    'rsi': recent['rsi'].iloc[i],
                })
        
        if len(green_candles) < 2:
            return []
        
        # Step 2: Find green candle with HIGHEST RSI (Peak 1)
        highest_rsi_green = max(green_candles, key=lambda x: x['rsi'])
        
        # Step 3: Look in last 5 candles for green candles
        recent_df = df.tail(5).reset_index(drop=True)
        recent_original_indices = df.tail(5).index
        recent_green_candles = []
        
        for i, orig_idx in zip(range(len(recent_df)), recent_original_indices):
            if recent_df['is_green'].iloc[i] and not pd.isna(recent_df['rsi'].iloc[i]):
                # SHORT: Only include if RSI is <= peak1 RSI (RSI must be LOWER)
                if recent_df['rsi'].iloc[i] <= highest_rsi_green['rsi']:
                    recent_green_candles.append({
                        'index': orig_idx,
                        'timestamp': recent_df['timestamp'].iloc[i],
                        'price': recent_df['high'].iloc[i],
                        'rsi': recent_df['rsi'].iloc[i],
                    })
        
        if len(recent_green_candles) == 0:
            return []
        
        # Step 4: Find green candle with HIGHEST PRICE among recent (Peak 2)
        recent_highest_price_green = max(recent_green_candles, key=lambda x: x['price'])
        
        # Step 5: Check if they are different candles
        if highest_rsi_green['index'] == recent_highest_price_green['index']:
            return []
        
        # Step 6: Calculate price rise percentage
        price_rise_pct = ((recent_highest_price_green['price'] - highest_rsi_green['price']) / 
                         highest_rsi_green['price']) * 100
        
        # Step 7: Require at least 1% price rise
        if price_rise_pct < 1.0:
            return []
        
        # Step 8: Count green candles between
        green_candles_between = self.count_green_candles_between(
            df, 
            highest_rsi_green['index'], 
            recent_highest_price_green['index']
        )
        
        # Step 9: Calculate RSI drop (Peak1 RSI - Peak2 RSI)
        rsi_drop = highest_rsi_green['rsi'] - recent_highest_price_green['rsi']
        
        # Step 10: Verify RSI is actually dropping (Peak2 RSI <= Peak1 RSI)
        if rsi_drop <= 0:  # RSI didn't drop
            return []
        
        # Step 11: Calculate strength
        strength = (green_candles_between * 10) + (rsi_drop * 2) + price_rise_pct
        
        signal = {
            'type': 'SHORT',
            'symbol': symbol,
            'first_price': highest_rsi_green['price'],
            'first_rsi': highest_rsi_green['rsi'],
            'first_time': highest_rsi_green['timestamp'].strftime('%H:%M'),
            'recent_price': recent_highest_price_green['price'],
            'recent_rsi': recent_highest_price_green['rsi'],
            'recent_time': recent_highest_price_green['timestamp'].strftime('%H:%M'),
            'price_change_pct': price_rise_pct,
            'rsi_change': -rsi_drop,
            'candles_between': green_candles_between,
            'strength': strength,
            'current_price': df['close'].iloc[-1],
            'current_rsi': df['rsi'].iloc[-1]
        }
        return [signal]
    
    def find_long_signals(self, df, symbol):
        """PURIFIED LONG SIGNAL - RED CANDLES (Bullish Divergence)
           RULE: Peak2 RSI must be >= Peak1 RSI (RSI rising while price falling)"""
        if df is None or len(df) < 30:
            return []
        
        recent = df.tail(30).reset_index(drop=True)
        original_indices = df.tail(30).index
        
        # Step 1: Find red candles with their RSI after closing
        red_candles = []
        for i, orig_idx in zip(range(len(recent)), original_indices):
            if recent['is_red'].iloc[i] and not pd.isna(recent['rsi'].iloc[i]):
                red_candles.append({
                    'index': orig_idx,
                    'timestamp': recent['timestamp'].iloc[i],
                    'price': recent['low'].iloc[i],  # Use low for red candles
                    'rsi': recent['rsi'].iloc[i],
                })
        
        if len(red_candles) < 2:
            return []
        
        # Step 2: Find red candle with LOWEST RSI (Peak 1)
        lowest_rsi_red = min(red_candles, key=lambda x: x['rsi'])
        
        # Step 3: Look in last 5 candles for red candles
        recent_df = df.tail(5).reset_index(drop=True)
        recent_original_indices = df.tail(5).index
        recent_red_candles = []
        
        for i, orig_idx in zip(range(len(recent_df)), recent_original_indices):
            if recent_df['is_red'].iloc[i] and not pd.isna(recent_df['rsi'].iloc[i]):
                # LONG: Only include if RSI is >= peak1 RSI (RSI must be HIGHER)
                if recent_df['rsi'].iloc[i] >= lowest_rsi_red['rsi']:
                    recent_red_candles.append({
                        'index': orig_idx,
                        'timestamp': recent_df['timestamp'].iloc[i],
                        'price': recent_df['low'].iloc[i],
                        'rsi': recent_df['rsi'].iloc[i],
                    })
        
        if len(recent_red_candles) == 0:
            return []
        
        # Step 4: Find red candle with LOWEST PRICE among recent (Peak 2)
        recent_lowest_price_red = min(recent_red_candles, key=lambda x: x['price'])
        
        # Step 5: Check if they are different candles
        if lowest_rsi_red['index'] == recent_lowest_price_red['index']:
            return []
        
        # Step 6: Calculate price drop percentage
        price_drop_pct = ((recent_lowest_price_red['price'] - lowest_rsi_red['price']) / 
                         lowest_rsi_red['price']) * 100
        
        # Step 7: Require at least 1% price drop
        if price_drop_pct > -1.0:  # More negative than -1% (e.g., -1.5%)
            return []
        
        # Step 8: Count red candles between
        red_candles_between = self.count_red_candles_between(
            df, 
            lowest_rsi_red['index'], 
            recent_lowest_price_red['index']
        )
        
        # Step 9: Calculate RSI rise (Peak2 RSI - Peak1 RSI)
        rsi_rise = recent_lowest_price_red['rsi'] - lowest_rsi_red['rsi']
        
        # Step 10: Verify RSI is actually rising (Peak2 RSI >= Peak1 RSI)
        if rsi_rise <= 0:  # RSI didn't rise
            return []
        
        # Step 11: Calculate strength
        strength = (red_candles_between * 10) + (rsi_rise * 2) + abs(price_drop_pct)
        
        signal = {
            'type': 'LONG',
            'symbol': symbol,
            'first_price': lowest_rsi_red['price'],
            'first_rsi': lowest_rsi_red['rsi'],
            'first_time': lowest_rsi_red['timestamp'].strftime('%H:%M'),
            'recent_price': recent_lowest_price_red['price'],
            'recent_rsi': recent_lowest_price_red['rsi'],
            'recent_time': recent_lowest_price_red['timestamp'].strftime('%H:%M'),
            'price_change_pct': price_drop_pct,
            'rsi_change': rsi_rise,
            'candles_between': red_candles_between,
            'strength': strength,
            'current_price': df['close'].iloc[-1],
            'current_rsi': df['rsi'].iloc[-1]
        }
        return [signal]
    
    def scan_coins(self, symbols):
        self.long_signals = []
        self.short_signals = []
        
        for symbol in symbols:
            try:
                df = self.fetch_candles(symbol)
                if df is None:
                    continue
                
                long_sigs = self.find_long_signals(df, symbol)
                for sig in long_sigs:
                    self.long_signals.append(sig)
                
                short_sigs = self.find_short_signals(df, symbol)
                for sig in short_sigs:
                    self.short_signals.append(sig)
                    
            except:
                continue
        
        # Sort by candles between (more candles = stronger)
        self.long_signals.sort(key=lambda x: x['candles_between'], reverse=True)
        self.short_signals.sort(key=lambda x: x['candles_between'], reverse=True)
        
        return self.long_signals, self.short_signals


# ============================================
# BOT 2: Chart Screenshot Bot (FUTURES - 180 CANDLES)  # CHANGED FROM 240 TO 180
# ============================================
class ChartScreenshotBot:
    def __init__(self, save_path=r"images"):
        self.save_path = save_path
        os.makedirs(save_path, exist_ok=True)
        
    def calculate_rsi(self, series, period=14):
        delta = series.diff(1)
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()
        rs = avg_gain / avg_loss.where(avg_loss != 0, 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def fetch_from_exchange(self, coin, exchange):
        symbol = coin.upper() + 'USDT'
        
        # Use Futures API endpoints with 180 CANDLES
        if exchange.lower() == 'binance':
            # Binance Futures API
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1m&limit=180"  # CHANGED TO 180
        elif exchange.lower() == 'mexc':
            # MEXC Futures API
            url = f"https://futures.mexc.com/api/v1/contract/kline/{symbol}?interval=1m&limit=180"  # CHANGED TO 180
        else:
            return None, None
        
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            if not data or not isinstance(data, list) or len(data) == 0:
                return None, None
        except:
            return None, None
        
        # Parse based on exchange
        if exchange.lower() == 'binance':
            df = pd.DataFrame(data, columns=['open_time', 'open', 'high', 'low', 'close', 'volume',
                                           'close_time', 'qav', 'num_trades', 'taker_base_vol',
                                           'taker_quote_vol', 'ignore'])
        else:  # mexc
            df = pd.DataFrame(data, columns=['open_time', 'open', 'high', 'low', 'close', 'volume',
                                           'close_time', 'quote_volume'])
        
        try:
            df = df.astype({'open': 'float', 'high': 'float', 'low': 'float', 'close': 'float'})
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            df['rsi14'] = self.calculate_rsi(df['close'], 14)
        except:
            return None, None
        
        return df, exchange
    
    def fetch_data(self, coin):
        # Try MEXC Futures first, then Binance Futures
        for exchange in ['mexc', 'binance']:
            df, used_exchange = self.fetch_from_exchange(coin, exchange)
            if df is not None:
                return df, used_exchange
        return None, None
    
    def create_chart(self, df, coin, exchange, signal_info=None):
        if df is None or len(df) == 0:
            return None
        
        style.use('dark_background')
        fig, (ax1, ax2) = plt.subplots(2, 1, gridspec_kw={'height_ratios': [3, 1]},
                                       figsize=(13, 7.5), dpi=130)  # Slightly smaller for 180 candles
        fig.patch.set_facecolor('#0d1117')
        
        # Candles - show all 180
        for i in range(len(df)):
            o = df['open'][i]
            c = df['close'][i]
            h = df['high'][i]
            l = df['low'][i]
            color = '#26a69a' if c >= o else '#ef5350'
            ax1.plot([i, i], [l, h], color='#a0a0a0', lw=1.0, zorder=1)
            ax1.add_patch(Rectangle((i - 0.3, min(o,c)), 0.6, abs(c-o),
                                    facecolor=color, edgecolor=color, lw=0.5, zorder=2))
        
        current = df['close'].iloc[-1]
        title = f"{current:,.4f} {coin.upper()}USDT PERPETUAL - {exchange.upper()} FUTURES (180 candles)"  # Added 180 candles label
        if signal_info:
            title += f" | {signal_info['type']} SIGNAL"
        ax1.set_title(title, color='white', fontsize=13, loc='left', pad=10)
        ax1.grid(True, color='#1e222d', ls='-', lw=0.5, alpha=0.6)
        ax1.tick_params(colors='white', labelsize=8)
        ax1.set_facecolor('#0d1117')
        ax1.xaxis.set_tick_params(labelbottom=False)
        
        # Highlight signal peaks
        if signal_info:
            first_time = signal_info['first_time']
            recent_time = signal_info['recent_time']
            
            # Find positions (last 30 candles only for visibility)
            last_30_idx = len(df) - 30
            first_pos = None
            recent_pos = None
            
            for i in range(last_30_idx, len(df)):
                time_str = df['open_time'].iloc[i].strftime('%H:%M')
                if time_str == first_time:
                    first_pos = i
                if time_str == recent_time:
                    recent_pos = i
            
            if first_pos is not None:
                color = 'lime' if signal_info['type'] == 'LONG' else 'yellow'
                marker = 'v' if signal_info['type'] == 'LONG' else '^'
                ax1.plot(first_pos, df['low' if signal_info['type'] == 'LONG' else 'high'].iloc[first_pos], 
                        marker, markersize=12, markeredgecolor='white', markerfacecolor=color, alpha=0.9)
            
            if recent_pos is not None:
                color = 'lime' if signal_info['type'] == 'LONG' else 'yellow'
                marker = 'v' if signal_info['type'] == 'LONG' else '^'
                ax1.plot(recent_pos, df['low' if signal_info['type'] == 'LONG' else 'high'].iloc[recent_pos], 
                        marker, markersize=12, markeredgecolor='white', markerfacecolor=color, alpha=0.9)
        
        # RSI
        ax2.plot(df['rsi14'], color='#bb86fc', lw=1.8)
        ax2.axhspan(30, 70, facecolor='#1e222d', alpha=0.3)
        ax2.axhline(70, color='#ffab91', ls='--', lw=1.1, alpha=0.8)
        ax2.axhline(30, color='#ffab91', ls='--', lw=1.1, alpha=0.8)
        ax2.text(len(df)*0.02, 73, '70', color='#ffab91', fontsize=9, va='bottom')
        ax2.text(len(df)*0.02, 27, '30', color='#ffab91', fontsize=9, va='top')
        
        ax2.set_ylim(0, 100)
        ax2.grid(True, color='#1e222d', ls='-', lw=0.5, alpha=0.6)
        ax2.tick_params(colors='white', labelsize=8)
        ax2.set_facecolor('#0d1117')
        ax2.set_title("RSI 14 - PERPETUAL FUTURES (3 hours)", color='white', fontsize=10, loc='left', pad=5)  # Updated to 3 hours (180 min)
        
        # Show fewer x-labels for 180 candles
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax2.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8))
        plt.setp(ax2.get_xticklabels(), rotation=0, ha='center', fontsize=7)
        
        fig.tight_layout()
        plt.subplots_adjust(hspace=0.1)
        return fig
    
    def save_chart(self, fig, coin, exchange, signal_info=None):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        signal_type = signal_info['type'] if signal_info else 'NOSIGNAL'
        filename = f"{coin.upper()}_{exchange.upper()}_FUTURES_180_{signal_type}_{timestamp}.png"  # Added 180 to filename
        save_path = os.path.join(self.save_path, filename)
        
        fig.savefig(save_path, dpi=140, bbox_inches='tight', facecolor=fig.get_facecolor())
        plt.close(fig)
        
        return save_path
    
    def capture_signal_chart(self, coin, signal_info):
        df, used_exchange = self.fetch_data(coin)
        if df is None:
            return None
        
        fig = self.create_chart(df, coin, used_exchange, signal_info)
        if fig is None:
            return None
        
        return self.save_chart(fig, coin, used_exchange, signal_info)


# ============================================
# BOT 3: Coinglass Scanner Bot - 80 COINS (40 LONG + 40 SHORT)
# ============================================
class CoinglassScannerBot:
    def __init__(self):
        self.driver = None
        self.long_coins = []
        self.short_coins = []
        self.is_running = False
        
    def start_browser(self):
        try:
            chrome_options = Options()
            chrome_options.add_argument("--window-size=1400,900")
            chrome_options.add_argument("--disable-notifications")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_experimental_option("detach", False)
            
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.get("https://www.coinglass.com/gainers-losers")
            time.sleep(5)
            self.select_15min_filter()
            self.is_running = True
            return True
        except Exception as e:
            return False
    
    def select_15min_filter(self):
        try:
            js_click = """
            var buttons = document.querySelectorAll('button');
            for(var btn of buttons) {
                if(btn.textContent.includes('15') || btn.textContent.includes('15m')) {
                    btn.click();
                    return true;
                }
            }
            return false;
            """
            self.driver.execute_script(js_click)
            time.sleep(1.5)
        except:
            pass
    
    def extract_coins(self):
        """Extract top 40 gainers and top 40 losers = 80 total coins"""
        if not self.driver:
            return [], []
        
        try:
            js_extract = """
            function extractCoinsInOrder() {
                var long = [];
                var short = [];
                
                var allTables = document.querySelectorAll('table');
                
                for(var table of allTables) {
                    var rows = table.querySelectorAll('tr');
                    
                    for(var row of rows) {
                        var cells = row.querySelectorAll('td');
                        if(cells.length < 2) continue;
                        
                        var symbolCell = cells[1];
                        if(!symbolCell) continue;
                        
                        var symbol = symbolCell.textContent.trim();
                        var rowText = row.textContent;
                        
                        if(symbol && symbol.length > 1 && symbol.length < 15 && 
                           !symbol.includes('$') && !symbol.includes('Price') && 
                           !symbol.includes('Symbol') && symbol.match(/^[A-Z0-9/]+$/)) {
                            
                            if(rowText.includes('+') || rowText.includes('▲') || 
                               row.className.includes('positive')) {
                                if(!long.includes(symbol)) {
                                    long.push(symbol);
                                }
                            }
                            else if(rowText.includes('-') || rowText.includes('▼') || 
                                    row.className.includes('negative')) {
                                if(!short.includes(symbol)) {
                                    short.push(symbol);
                                }
                            }
                        }
                    }
                }
                
                return {long: long, short: short};
            }
            return extractCoinsInOrder();
            """
            
            result = self.driver.execute_script(js_extract)
            
            self.long_coins = []
            self.short_coins = []
            
            for coin in result.get('long', []):
                if coin and self.is_valid_coin(coin):
                    self.long_coins.append(coin)
            
            for coin in result.get('short', []):
                if coin and self.is_valid_coin(coin):
                    self.short_coins.append(coin)
            
            # Return top 40 long and top 40 short = 80 total coins
            return self.long_coins[:40], self.short_coins[:40]  # 80 total coins
            
        except Exception as e:
            return [], []
    
    def is_valid_coin(self, coin):
        if not coin or len(coin) < 2 or len(coin) > 12:
            return False
        
        invalid = ['Symbol', 'Price', 'Volume', 'Change', '24h', 'Long', 'Short', 
                  'Trade', 'API', 'Login', 'Market', 'Open', 'Interest', 'Funding']
        
        return coin not in invalid and re.match(r'^[A-Z0-9/]{2,12}$', coin) is not None
    
    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
            self.is_running = False


# ============================================
# TELEGRAM BOT - DETAILED FORMAT
# ============================================
class TelegramBot:
    def __init__(self, token=TELEGRAM_BOT_TOKEN, channel_id=TELEGRAM_CHANNEL_ID):
        self.token = token
        self.channel_id = channel_id
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.enabled = token != "YOUR_BOT_TOKEN_HERE" and channel_id != "@YOUR_CHANNEL_USERNAME"
        
    def send_message(self, text):
        """Send text message to Telegram channel"""
        if not self.enabled:
            return False
            
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id': self.channel_id,
                'text': text,
                'parse_mode': 'HTML'
            }
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"Telegram send message error: {e}")
            return False
    
    def send_photo(self, photo_path, caption=""):
        """Send photo with caption to Telegram channel"""
        if not self.enabled:
            return False
            
        try:
            url = f"{self.base_url}/sendPhoto"
            
            with open(photo_path, 'rb') as photo:
                files = {'photo': photo}
                data = {'chat_id': self.channel_id, 'caption': caption}
                response = requests.post(url, files=files, data=data, timeout=30)
            
            return response.status_code == 200
        except Exception as e:
            print(f"Telegram send photo error: {e}")
            return False
    
    def format_signal_message(self, signal):
        """Format signal for Telegram message"""
        coin = signal['symbol'].replace('USDT', '')
        signal_type = signal['type']
        
        # Emoji based on signal type
        if signal_type == "LONG":
            main_emoji = "🟢"
            candle_type = "🔴 RED"
            arrow = "📈"
            rule = "RSI Rising 📈"
        else:
            main_emoji = "🔴"
            candle_type = "🟢 GREEN"
            arrow = "📉"
            rule = "RSI Falling 📉"
        
        message = f"""{main_emoji} {signal_type} {arrow} {coin} PERPETUAL (180 candles)

🔹 Peak1: ${signal['first_price']:.4f} (RSI {signal['first_rsi']:.1f}) {signal['first_time']}
🔹 Peak2: ${signal['recent_price']:.4f} (RSI {signal['recent_rsi']:.1f}) {signal['recent_time']}
{candle_type} candles between: {signal['candles_between']}
📊 RSI change: {signal['rsi_change']:+.1f} ({rule})
💪 Strength: {signal['strength']:.1f}
✅ 1% minimum move achieved"""
        
        return message
    
    def send_signal(self, signal, chart_path=None):
        """Send signal to Telegram with optional chart image"""
        if not self.enabled:
            return False
            
        message = self.format_signal_message(signal)
        
        if chart_path and os.path.exists(chart_path):
            return self.send_photo(chart_path, message)
        else:
            return self.send_message(message)


# ============================================
# MAIN GUI APPLICATION
# ============================================
class AllInOneTradingBot:
    def __init__(self, root):
        self.root = root
        self.root.title("🚀 PURIFIED FUTURES DIVERGENCE BOT (80 Coins - 180 CANDLES)")
        self.root.geometry("1300x850")
        self.root.configure(bg='#0a0a0a')
        
        # Initialize bots
        self.bot1 = CandleColorDivergenceBot()
        self.bot2 = ChartScreenshotBot(r"images")
        self.bot3 = CoinglassScannerBot()
        self.telegram = TelegramBot()
        
        # Variables
        self.is_running = False
        self.scan_thread = None
        self.update_queue = queue.Queue()
        self.long_signals = []
        self.short_signals = []
        self.current_coins = []
        
        # Setup GUI
        self.setup_ui()
        
        # Start queue checker
        self.check_queue()
        
        # Show Telegram status
        if self.telegram.enabled:
            self.log("✅ Telegram bot configured and ready")
        else:
            self.log("⚠️ Telegram bot not configured")
        
    def setup_ui(self):
        # Title
        title_frame = tk.Frame(self.root, bg='#0a0a0a')
        title_frame.pack(pady=15)
        
        title_label = tk.Label(title_frame, text="🤖 PURIFIED FUTURES DIVERGENCE BOT (80 PERPETUAL COINS - 180 CANDLES)", 
                              font=('Arial', 20, 'bold'), 
                              bg='#0a0a0a', fg='#00ff88')
        title_label.pack()
        
        subtitle_label = tk.Label(title_frame, 
                                 text="✅ CORRECTED: LONG (RSI ≥) | SHORT (RSI ≤) | 1% Min Move | 180-Candle Charts (3 hours) | Perpetual Futures",
                                 font=('Arial', 10), 
                                 bg='#0a0a0a', fg='#f39c12')
        subtitle_label.pack()
        
        # Control Panel
        control_frame = tk.Frame(self.root, bg='#1a1a1a', relief=tk.RAISED, bd=2)
        control_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # Start/Stop Button
        self.start_btn = tk.Button(control_frame, text="🚀 START ALL BOTS", 
                                  command=self.toggle_bots,
                                  bg='#2ecc71', fg='white', font=('Arial', 12, 'bold'),
                                  padx=20, pady=10, border=0, cursor='hand2')
        self.start_btn.pack(side=tk.LEFT, padx=20, pady=10)
        
        # Status Indicators
        status_frame = tk.Frame(control_frame, bg='#1a1a1a')
        status_frame.pack(side=tk.LEFT, padx=20)
        
        # Bot 1 Status
        self.bot1_status = tk.Label(status_frame, text="⚫ Bot 1: OFF", 
                                   font=('Arial', 10, 'bold'),
                                   bg='#1a1a1a', fg='#888888')
        self.bot1_status.pack(side=tk.LEFT, padx=10)
        
        # Bot 2 Status
        self.bot2_status = tk.Label(status_frame, text="⚫ Bot 2: OFF", 
                                   font=('Arial', 10, 'bold'),
                                   bg='#1a1a1a', fg='#888888')
        self.bot2_status.pack(side=tk.LEFT, padx=10)
        
        # Bot 3 Status
        self.bot3_status = tk.Label(status_frame, text="⚫ Bot 3: OFF", 
                                   font=('Arial', 10, 'bold'),
                                   bg='#1a1a1a', fg='#888888')
        self.bot3_status.pack(side=tk.LEFT, padx=10)
        
        # Telegram Status
        telegram_color = '#2ecc71' if self.telegram.enabled else '#e74c3c'
        telegram_text = "✅ Telegram: ON" if self.telegram.enabled else "❌ Telegram: OFF"
        self.telegram_status = tk.Label(status_frame, text=telegram_text, 
                                       font=('Arial', 10, 'bold'),
                                       bg='#1a1a1a', fg=telegram_color)
        self.telegram_status.pack(side=tk.LEFT, padx=10)
        
        # Timer and Stats
        stats_frame = tk.Frame(control_frame, bg='#1a1a1a')
        stats_frame.pack(side=tk.RIGHT, padx=20)
        
        self.timer_label = tk.Label(stats_frame, text="⏱ Next scan: --s", 
                                   font=('Arial', 10, 'bold'),
                                   bg='#1a1a1a', fg='#3498db')
        self.timer_label.pack(side=tk.LEFT, padx=10)
        
        self.scan_count_label = tk.Label(stats_frame, text="📊 Scans: 0", 
                                        font=('Arial', 10, 'bold'),
                                        bg='#1a1a1a', fg='#9b59b6')
        self.scan_count_label.pack(side=tk.LEFT, padx=10)
        
        # Main Content Area
        content_frame = tk.Frame(self.root, bg='#0a0a0a')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Left Column - Live Log
        left_frame = tk.Frame(content_frame, bg='#1a1a1a', relief=tk.RAISED, bd=2)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        tk.Label(left_frame, text="📋 LIVE ACTIVITY LOG", 
                font=('Arial', 12, 'bold'), bg='#1a1a1a', fg='#00ff88').pack(pady=5)
        
        self.log_text = scrolledtext.ScrolledText(left_frame, 
                                                  wrap=tk.WORD, 
                                                  width=50, 
                                                  height=30,
                                                  bg='#0f1420',
                                                  fg='#00ff88',
                                                  insertbackground='white',
                                                  font=('Courier', 10))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Right Column - Signals Display
        right_frame = tk.Frame(content_frame, bg='#1a1a1a', relief=tk.RAISED, bd=2)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)
        
        tk.Label(right_frame, text="🚨 PURIFIED SIGNALS - PERPETUAL FUTURES (180 candles)", 
                font=('Arial', 12, 'bold'), bg='#1a1a1a', fg='#ff6b6b').pack(pady=5)
        
        # Signal tabs
        self.signal_notebook = ttk.Notebook(right_frame)
        self.signal_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # LONG Signals Tab
        self.long_frame = tk.Frame(self.signal_notebook, bg='#0f1420')
        self.signal_notebook.add(self.long_frame, text='🟢 LONG SIGNALS')
        
        self.long_signals_text = scrolledtext.ScrolledText(self.long_frame, 
                                                           wrap=tk.WORD, 
                                                           width=50, 
                                                           height=28,
                                                           bg='#0f1420',
                                                           fg='#2ecc71',
                                                           insertbackground='white',
                                                           font=('Courier', 10))
        self.long_signals_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # SHORT Signals Tab
        self.short_frame = tk.Frame(self.signal_notebook, bg='#0f1420')
        self.signal_notebook.add(self.short_frame, text='🔴 SHORT SIGNALS')
        
        self.short_signals_text = scrolledtext.ScrolledText(self.short_frame, 
                                                            wrap=tk.WORD, 
                                                            width=50, 
                                                            height=28,
                                                            bg='#0f1420',
                                                            fg='#ff6b6b',
                                                            insertbackground='white',
                                                            font=('Courier', 10))
        self.short_signals_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Bottom Control Buttons
        bottom_frame = tk.Frame(self.root, bg='#0a0a0a')
        bottom_frame.pack(fill=tk.X, padx=20, pady=10)
        
        buttons = [
            ("📋 COPY LONG", self.copy_long, '#2ecc71'),
            ("📋 COPY SHORT", self.copy_short, '#ff6b6b'),
            ("📸 OPEN IMAGES FOLDER", self.open_images_folder, '#3498db'),
            ("🌐 OPEN MEXC FUTURES", self.open_mexc, '#9b59b6'),
            ("📱 TEST TELEGRAM", self.test_telegram, '#0088cc'),
            ("🗑 CLEAR LOG", self.clear_log, '#95a5a6')
        ]
        
        for text, command, color in buttons:
            btn = tk.Button(bottom_frame, text=text, command=command,
                          bg=color, fg='white', font=('Arial', 9, 'bold'),
                          padx=15, pady=8, border=0, cursor='hand2')
            btn.pack(side=tk.LEFT, padx=5)
    
    def test_telegram(self):
        """Test Telegram connection"""
        if not self.telegram.enabled:
            messagebox.showerror("Telegram Error", 
                                "Telegram not configured!")
            return
        
        test_signal = {
            'type': 'LONG',
            'symbol': 'BTCUSDT',
            'first_price': 50000.00,
            'first_rsi': 25.5,
            'first_time': '10:30',
            'recent_price': 49500.00,
            'recent_rsi': 32.2,
            'recent_time': '10:35',
            'price_change_pct': -1.0,
            'rsi_change': 6.7,
            'candles_between': 4,
            'strength': 85.5,
            'current_price': 49600.00,
            'current_rsi': 33.8
        }
        
        self.log("📱 Testing Telegram connection with corrected LONG signal...")
        
        if self.telegram.send_signal(test_signal):
            self.log("✅ Test signal sent to Telegram!")
            messagebox.showinfo("Telegram Test", "Test signal sent successfully!")
        else:
            self.log("❌ Failed to send test signal")
            messagebox.showerror("Telegram Test", "Failed to send signal.")
    
    def toggle_bots(self):
        if not self.is_running:
            self.is_running = True
            self.start_btn.config(text="⏹ STOP ALL BOTS", bg='#e74c3c')
            
            self.log("🚀 Starting Bot 3: Coinglass Scanner (80 coins)...")
            self.bot3_status.config(text="🟡 Bot 3: STARTING", fg="#f39c12")
            
            thread = threading.Thread(target=self.start_coinglass, daemon=True)
            thread.start()
        else:
            self.is_running = False
            self.start_btn.config(text="🚀 START ALL BOTS", bg='#2ecc71')
            self.bot1_status.config(text="⚫ Bot 1: OFF", fg="#888888")
            self.bot2_status.config(text="⚫ Bot 2: OFF", fg="#888888")
            self.bot3_status.config(text="⚫ Bot 3: OFF", fg="#888888")
            self.bot3.close()
            self.log("⏹ Bots stopped")
    
    def start_coinglass(self):
        success = self.bot3.start_browser()
        if success:
            self.update_queue.put(("status", "bot3", "🟢 Bot 3: ACTIVE", "#2ecc71"))
            self.update_queue.put(("log", "✅ Bot 3: Coinglass browser started"))
            
            self.start_scan_loop()
        else:
            self.update_queue.put(("status", "bot3", "🔴 Bot 3: FAILED", "#e74c3c"))
            self.update_queue.put(("log", "❌ Bot 3: Failed to start browser"))
            self.is_running = False
            self.start_btn.config(text="🚀 START ALL BOTS", bg='#2ecc71')
    
    def start_scan_loop(self):
        scan_count = 0
        
        while self.is_running:
            scan_count += 1
            self.update_queue.put(("scan_count", scan_count))
            
            for i in range(60, 0, -1):
                if not self.is_running:
                    break
                self.update_queue.put(("timer", i))
                time.sleep(1)
            
            if not self.is_running:
                break
            
            self.update_queue.put(("log", f"\n{'='*50}"))
            self.update_queue.put(("log", f"📊 SCAN #{scan_count} - {datetime.now().strftime('%H:%M:%S')}"))
            self.update_queue.put(("log", f"{'='*50}"))
            
            # Extract 80 coins from Coinglass
            self.update_queue.put(("status", "bot3", "🟡 Bot 3: EXTRACTING", "#f39c12"))
            self.update_queue.put(("log", "🔍 Bot 3: Extracting 80 coins from Coinglass..."))
            
            long_coins, short_coins = self.bot3.extract_coins()
            self.current_coins = long_coins + short_coins
            
            self.update_queue.put(("log", f"✅ Found {len(long_coins)} LONG candidates | {len(short_coins)} SHORT candidates"))
            self.update_queue.put(("log", f"📊 TOTAL COINS TO SCAN: {len(self.current_coins)}/80"))
            
            if not self.current_coins:
                self.update_queue.put(("log", "⚠ No coins found, skipping scan"))
                self.update_queue.put(("status", "bot3", "🟢 Bot 3: ACTIVE", "#2ecc71"))
                continue
            
            # Run divergence scan with CORRECTED logic
            self.update_queue.put(("status", "bot1", "🟡 Bot 1: SCANNING", "#f39c12"))
            self.update_queue.put(("log", f"🔍 Bot 1: Scanning {len(self.current_coins)} coins for PURIFIED divergence..."))
            self.update_queue.put(("log", "   ✅ LONG: RSI must rise (Peak2 RSI ≥ Peak1 RSI)"))
            self.update_queue.put(("log", "   ✅ SHORT: RSI must fall (Peak2 RSI ≤ Peak1 RSI)"))
            self.update_queue.put(("log", "   ✅ Minimum 1% price move required"))
            
            coins_with_usdt = [c + 'USDT' if not c.endswith('USDT') else c for c in self.current_coins]
            
            long_signals, short_signals = self.bot1.scan_coins(coins_with_usdt)
            
            self.update_queue.put(("log", f"✅ Bot 1: Found {len(long_signals)} PURIFIED LONG | {len(short_signals)} PURIFIED SHORT signals"))
            self.update_queue.put(("status", "bot1", "🟢 Bot 1: ACTIVE", "#2ecc71"))
            
            # Take screenshots of top signals
            self.update_queue.put(("status", "bot2", "🟡 Bot 2: CAPTURING 180-CANDLE CHARTS", "#f39c12"))
            
            all_signals = []
            
            # Process top 8 LONG signals
            for i, signal in enumerate(long_signals[:8]):
                coin = signal['symbol'].replace('USDT', '')
                self.update_queue.put(("log", f"📸 Bot 2: Capturing 180-candle FUTURES chart for {coin} LONG..."))
                self.update_queue.put(("log", f"   Peak1 RSI: {signal['first_rsi']:.1f} → Peak2 RSI: {signal['recent_rsi']:.1f} (RSI rose {signal['rsi_change']:+.1f})"))
                
                chart_path = self.bot2.capture_signal_chart(coin, signal)
                if chart_path:
                    signal['chart_path'] = chart_path
                    all_signals.append(signal)
                    self.update_queue.put(("log", f"   ✅ 180-candle chart saved: {os.path.basename(chart_path)}"))
                    
                    if self.telegram.enabled:
                        self.update_queue.put(("log", f"   📱 Sending to Telegram..."))
                        if self.telegram.send_signal(signal, chart_path):
                            self.update_queue.put(("log", f"   ✅ Signal sent to Telegram"))
                        else:
                            self.update_queue.put(("log", f"   ❌ Failed to send to Telegram"))
            
            # Process top 8 SHORT signals
            for i, signal in enumerate(short_signals[:8]):
                coin = signal['symbol'].replace('USDT', '')
                self.update_queue.put(("log", f"📸 Bot 2: Capturing 180-candle FUTURES chart for {coin} SHORT..."))
                self.update_queue.put(("log", f"   Peak1 RSI: {signal['first_rsi']:.1f} → Peak2 RSI: {signal['recent_rsi']:.1f} (RSI dropped {abs(signal['rsi_change']):.1f})"))
                
                chart_path = self.bot2.capture_signal_chart(coin, signal)
                if chart_path:
                    signal['chart_path'] = chart_path
                    all_signals.append(signal)
                    self.update_queue.put(("log", f"   ✅ 180-candle chart saved: {os.path.basename(chart_path)}"))
                    
                    if self.telegram.enabled:
                        self.update_queue.put(("log", f"   📱 Sending to Telegram..."))
                        if self.telegram.send_signal(signal, chart_path):
                            self.update_queue.put(("log", f"   ✅ Signal sent to Telegram"))
                        else:
                            self.update_queue.put(("log", f"   ❌ Failed to send to Telegram"))
            
            self.update_queue.put(("status", "bot2", "🟢 Bot 2: ACTIVE", "#2ecc71"))
            
            # Update signals display
            self.update_queue.put(("update_signals", long_signals, short_signals))
            
            # Summary
            self.update_queue.put(("log", f"\n✅ SCAN COMPLETE: {len(long_signals)} PURIFIED LONG | {len(short_signals)} PURIFIED SHORT signals"))
            self.update_queue.put(("log", f"📸 180-candle FUTURES charts (3 hours): {len(all_signals)} signals with charts"))
            self.update_queue.put(("log", f"📊 Scanned {len(self.current_coins)} PERPETUAL FUTURES coins"))
            self.update_queue.put(("log", "✅ All signals follow CORRECT divergence rules"))
            
            self.update_queue.put(("status", "bot3", "🟢 Bot 3: ACTIVE", "#2ecc71"))
    
    def update_signals_display(self, long_signals, short_signals):
        # Clear
        self.long_signals_text.delete(1.0, tk.END)
        self.short_signals_text.delete(1.0, tk.END)
        
        # Show LONG signals
        if long_signals:
            for i, sig in enumerate(long_signals[:10], 1):
                signal_text = self.format_signal_condensed(sig)
                self.long_signals_text.insert(tk.END, signal_text + "\n")
                self.long_signals_text.insert(tk.END, "-" * 50 + "\n")
        else:
            self.long_signals_text.insert(tk.END, "✨ No PURIFIED LONG signals found\n")
            self.long_signals_text.insert(tk.END, "   Rule: RSI must rise (Peak2 ≥ Peak1)\n")
        
        # Show SHORT signals
        if short_signals:
            for i, sig in enumerate(short_signals[:10], 1):
                signal_text = self.format_signal_condensed(sig)
                self.short_signals_text.insert(tk.END, signal_text + "\n")
                self.short_signals_text.insert(tk.END, "-" * 50 + "\n")
        else:
            self.short_signals_text.insert(tk.END, "✨ No PURIFIED SHORT signals found\n")
            self.short_signals_text.insert(tk.END, "   Rule: RSI must fall (Peak2 ≤ Peak1)\n")
    
    def format_signal_condensed(self, sig):
        """Format signal in condensed version"""
        coin = sig['symbol'].replace('USDT', '')
        signal_type = sig['type']
        emoji = "🟢" if signal_type == "LONG" else "🔴"
        candle_type = "🔴 RED" if signal_type == "LONG" else "🟢 GREEN"
        
        lines = []
        lines.append(f"{emoji} {coin} - {signal_type} PERPETUAL (180 candles)")
        lines.append(f"   🔹 Peak1: ${sig['first_price']:.4f} (RSI {sig['first_rsi']:.1f}) {sig['first_time']}")
        lines.append(f"   🔹 Peak2: ${sig['recent_price']:.4f} (RSI {sig['recent_rsi']:.1f}) {sig['recent_time']}")
        lines.append(f"   {candle_type} candles between: {sig['candles_between']}")
        lines.append(f"   📊 RSI change: {sig['rsi_change']:+.1f}")
        lines.append(f"   💪 Strength: {sig['strength']:.1f}")
        
        # Add rule indicator
        if signal_type == "LONG":
            lines.append(f"   ✅ Rule: RSI rose (Peak2 ≥ Peak1)")
        else:
            lines.append(f"   ✅ Rule: RSI fell (Peak2 ≤ Peak1)")
        
        if 'chart_path' in sig:
            lines.append(f"   📸 180-candle FUTURES chart saved")
        
        if self.telegram.enabled and 'chart_path' in sig:
            lines.append(f"   📱 Sent to Telegram")
        
        return "\n".join(lines)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
    
    def check_queue(self):
        try:
            while True:
                msg = self.update_queue.get_nowait()
                
                if msg[0] == "status":
                    _, bot, text, color = msg
                    if bot == "bot1":
                        self.bot1_status.config(text=text, fg=color)
                    elif bot == "bot2":
                        self.bot2_status.config(text=text, fg=color)
                    elif bot == "bot3":
                        self.bot3_status.config(text=text, fg=color)
                
                elif msg[0] == "log":
                    _, text = msg
                    self.log(text)
                
                elif msg[0] == "timer":
                    _, seconds = msg
                    self.timer_label.config(text=f"⏱ Next scan: {seconds}s")
                
                elif msg[0] == "scan_count":
                    _, count = msg
                    self.scan_count_label.config(text=f"📊 Scans: {count}")
                
                elif msg[0] == "update_signals":
                    _, long_sigs, short_sigs = msg
                    self.update_signals_display(long_sigs, short_sigs)
                
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.check_queue)
    
    def copy_long(self):
        text = self.long_signals_text.get(1.0, tk.END)
        if text.strip():
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.log("📋 LONG signals copied to clipboard")
    
    def copy_short(self):
        text = self.short_signals_text.get(1.0, tk.END)
        if text.strip():
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.log("📋 SHORT signals copied to clipboard")
    
    def open_images_folder(self):
        os.startfile(r"images")
    
    def open_mexc(self):
        webbrowser.open("https://futures.mexc.com/en-US/exchange")
    
    def clear_log(self):
        self.log_text.delete(1.0, tk.END)
    
    def __del__(self):
        self.bot3.close()


# ============================================
# MAIN
# ============================================
if __name__ == "__main__":
    root = tk.Tk()
    app = AllInOneTradingBot(root)
    root.mainloop()