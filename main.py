import yfinance as yf
import pandas as pd
import requests
import io
import time
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import platform
import subprocess

ui_queue = queue.Queue()
voice_queue = queue.Queue()

def voice_worker():
    system_os = platform.system()
    while True:
        text = voice_queue.get()
        clean_text = text.replace("'", "").replace('"', '')
        
        try:
            if system_os == "Windows":
                ps_cmd = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{clean_text}')"
                creation_flag = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
                subprocess.run(["powershell", "-Command", ps_cmd], creationflags=creation_flag)
            elif system_os == "Darwin":
                subprocess.run(["say", clean_text])
            else:
                subprocess.run(["espeak", clean_text])
        except Exception as e:
            print(f"Voice error: {e}")
            
        voice_queue.task_done()

threading.Thread(target=voice_worker, daemon=True).start()

def fetch_all_nse_stocks():
    url = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        df = pd.read_csv(io.StringIO(response.text))
        stock_dict = {}
        for index, row in df.iterrows():
            name = str(row['NAME OF COMPANY']).strip()
            raw_symbol = str(row['SYMBOL']).strip()
            yahoo_symbol = raw_symbol + ".NS" 
            display_name = f"{name} ({raw_symbol})"
            stock_dict[display_name] = yahoo_symbol
        return stock_dict
    except Exception:
        return {"Reliance Industries (RELIANCE)": "RELIANCE.NS"}

INDIAN_STOCKS = fetch_all_nse_stocks()
STOCK_NAMES = list(INDIAN_STOCKS.keys())

def get_stock_data(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="5d")
        if len(hist) < 2: 
            return None, None
        current_price = hist['Close'].iloc[-1]
        previous_close = hist['Close'].iloc[-2]
        pct_change = ((current_price - previous_close) / previous_close) * 100
        return current_price, pct_change
    except Exception:
        return None, None

def run_assistant(main_name, watchlist_names, interval, threshold):
    main_ticker = INDIAN_STOCKS[main_name]
    watchlist_tickers = [INDIAN_STOCKS[name] for name in watchlist_names]
    last_alerted_pcts = {}
    last_main_announce_time = 0
    
    start_msg = f"Assistant started. Monitoring {main_name.split(' (')[0]}."
    ui_queue.put((">>> ", start_msg))
    voice_queue.put(start_msg)
    
    while True:
        current_time = time.time()
        all_tickers_to_check = [main_ticker] + [t for t in watchlist_tickers if t != main_ticker]
        all_names_to_check = [main_name] + [n for n, t in zip(watchlist_names, watchlist_tickers) if t != main_ticker]
        
        for name, ticker in zip(all_names_to_check, all_tickers_to_check):
            price, p_change = get_stock_data(ticker)
            
            if price is not None:
                last_pct = last_alerted_pcts.get(ticker, 0)
                is_major_move = (p_change >= threshold or p_change <= -threshold)
                
                if is_major_move and abs(p_change - last_pct) >= 0.1:
                    short_name = name.split(' (')[0]
                    direction = "up" if p_change > 0 else "down"
                    alert = f"Alert! {short_name} is {direction} {abs(p_change):.1f} percent, at {price:.2f} rupees."
                    
                    ui_queue.put(("*** ", alert))
                    voice_queue.put(alert)
                    last_alerted_pcts[ticker] = p_change
                    
                    if ticker == main_ticker:
                        last_main_announce_time = current_time

        if current_time - last_main_announce_time >= interval:
            c_price, c_change = get_stock_data(main_ticker)
            if c_price is not None:
                dir_str = "up" if c_change >= 0 else "down"
                announcement = f"Update: {main_name.split(' (')[0]} is at {c_price:.2f} rupees, {dir_str} {abs(c_change):.1f} percent today."
                ui_queue.put(("-> ", announcement))
                voice_queue.put(announcement)
                
            last_main_announce_time = current_time
            
        time.sleep(5)

def process_ui_queue():
    try:
        while True:
            prefix, text = ui_queue.get_nowait()
            full_msg = f"{prefix}{text}"
            log_text.insert(tk.END, full_msg + "\n")
            log_text.see(tk.END)
    except queue.Empty:
        pass
    root.after(100, process_ui_queue)

def start_clicked():
    main_stock = main_combo.get()
    selected_indices = watch_listbox.curselection()
    watchlist_stocks = [watch_listbox.get(i) for i in selected_indices]
    
    try:
        interval = int(interval_entry.get())
        threshold = float(threshold_entry.get())
    except ValueError:
        messagebox.showerror("Error", "Please enter numbers for interval and threshold.")
        return
        
    if main_stock not in STOCK_NAMES:
        messagebox.showerror("Error", "Please select a valid main stock from the dropdown.")
        return
        
    start_button.config(state="disabled", text="Assistant is Running...")
    thread = threading.Thread(target=run_assistant, args=(main_stock, watchlist_stocks, interval, threshold), daemon=True)
    thread.start()

root = tk.Tk()
root.title("Full Market Voice Assistant")
root.geometry("550x750") 

tk.Label(root, text="1. Select Main Stock (Reads constantly):", font=("Arial", 10, "bold")).pack(pady=5)
main_combo = ttk.Combobox(root, values=STOCK_NAMES, width=60)
if len(STOCK_NAMES) > 0:
    main_combo.set(STOCK_NAMES[0]) 
main_combo.pack(pady=5)

tk.Label(root, text="2. Select Background Stocks:\n(Hold CTRL to click multiple)", font=("Arial", 10, "bold")).pack(pady=5)
frame = tk.Frame(root)
frame.pack(pady=5)
scrollbar = tk.Scrollbar(frame)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

watch_listbox = tk.Listbox(frame, selectmode=tk.MULTIPLE, yscrollcommand=scrollbar.set, width=60, height=8)
for stock in STOCK_NAMES:
    watch_listbox.insert(tk.END, stock) 
watch_listbox.pack(side=tk.LEFT)
scrollbar.config(command=watch_listbox.yview)

tk.Label(root, text="3. Check every X seconds:", font=("Arial", 10, "bold")).pack(pady=5)
interval_entry = tk.Entry(root, width=15)
interval_entry.insert(0, "60") 
interval_entry.pack(pady=5)

tk.Label(root, text="4. Major Alert Threshold (%):", font=("Arial", 10, "bold")).pack(pady=5)
threshold_entry = tk.Entry(root, width=15)
threshold_entry.insert(0, "2.0") 
threshold_entry.pack(pady=5)

start_button = tk.Button(root, text="Start Assistant", font=("Arial", 12, "bold"), bg="#4CAF50", fg="white", command=start_clicked)
start_button.pack(pady=10)

log_text = tk.Text(root, height=10, width=65, font=("Arial", 9))
log_text.pack(pady=10)
log_text.insert(tk.END, "System log will appear here...\n")

root.after(100, process_ui_queue)
root.mainloop()
