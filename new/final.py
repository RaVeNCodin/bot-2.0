import cv2
import numpy as np
import pyautogui
import time
from binance.client import Client
from binance.exceptions import BinanceAPIException
import threading
import pytesseract
region = (300, 955, 400, 18)
last_seen_text = None

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'  # change path as needed


api_key = 'pfoHrMYxFOzZxIBdBH11dP1BJ7iwuaQfkb88fC5H2bNGFfYBVfjPm1GB8VjyEWIY'
api_secret = 'ksn75QmMjtMHQGU9OgWOFsJdfiURh5DxSDXzqRvVAisUvDMrqiLm0OTYKJsP1Sb4'



client = Client(api_key, api_secret)

account_info = client.futures_account()

# Initialize the open trades dictionary
open_trades = {}

# Fetch the exchange information
exchange_info = client.futures_exchange_info()

# Create a dictionary to save the quantity precision for each symbol
quantity_precision = {}

# Iterate over the symbols
for symbol_info in exchange_info["symbols"]:
    symbol = symbol_info["symbol"]
    # Save the quantity precision in the dictionary
    quantity_precision[symbol] = symbol_info["quantityPrecision"]


# Function to adjust the quantity precision
def adjust_quantity_precision(quantity, symbol):
    # Fetch the maximum allowed precision for the symbol
    precision = quantity_precision[symbol]
    # Adjust the quantity to the maximum allowed precision and return it
    return round(quantity, precision)


# Function to handle selling
def sell(symbol, quantity, is_take_profit=False):
    try:
        client.futures_change_leverage(symbol=symbol, leverage=3)
        # Create a new order
        order = client.futures_create_order(
            symbol=symbol,
            side=Client.SIDE_SELL,
            type=Client.ORDER_TYPE_MARKET,
            quantity=adjust_quantity_precision(quantity, symbol))  # Precision adjustment

        # Set stop loss
        client.futures_create_order(
            symbol=symbol,
            side=Client.SIDE_BUY,
            quantity=adjust_quantity_precision(quantity, symbol))  # Precision adjustment

        # Update the open trades dictionary only if it's not a take profit order
        if not is_take_profit:
            if symbol in open_trades:
                open_trades[symbol]["remaining_quantity"] -= quantity
                if open_trades[symbol]["remaining_quantity"] <= 0:
                    del open_trades[symbol]
            else:
                print("No open position found.")

        return order
    except BinanceAPIException as e:
        print(e)
        return None


# Function to handle buying
def buy(symbol, quantity, is_take_profit=False):
    try:
        # Create a new order
        order = client.futures_create_order(
            symbol=symbol,
            side=Client.SIDE_BUY,
            type=Client.ORDER_TYPE_MARKET,
            quantity=adjust_quantity_precision(quantity, symbol))  # Precision adjustment

        client.futures_change_leverage(symbol=symbol, leverage=3)
        # Update the open trades dictionary only if it's not a take profit order
        if not is_take_profit:
            if symbol in open_trades:
                open_trades[symbol]["remaining_quantity"] += quantity
            else:
                open_trades[symbol] = {"remaining_quantity": quantity}

        client.futures_create_order(
            symbol=symbol,
            side=Client.SIDE_SELL,
            quantity=adjust_quantity_precision(quantity, symbol))  # Precision adjustment

        return order
    except BinanceAPIException as e:
        print(e)
        return None


# Update the open trades dictionary
def update_open_trades():
    try:
        # Fetch the account information
        account_info = client.futures_account()

        # Clear the open_trades dictionary
        open_trades.clear()

        # Iterate over the positions and update the open_trades dictionary
        for position in account_info["positions"]:
            symbol = position["symbol"]
            quantity = float(position["positionAmt"])
            if quantity != 0:
                open_trades[symbol] = {"remaining_quantity": quantity}

    except BinanceAPIException as e:
        print(e)


# Close a trade with a market order
# Updated take_profit function
def take_profit(symbol, percentage, position_type):
    # Update the open trades dictionary
    update_open_trades()

    # If no open position, return None
    if symbol not in open_trades:
        print("No open position found.")
        return None

    # Calculate the quantity to close
    quantity = abs(open_trades[symbol]["remaining_quantity"]) * percentage

    # Determine the side (buy/sell) based on the remaining quantity
    side = Client.SIDE_BUY if position_type == "short" else Client.SIDE_SELL

    # Send a market order to close the trade with the specified quantity
    order = client.futures_create_order(
        symbol=symbol,
        side=side,
        type=Client.ORDER_TYPE_MARKET,
        quantity=adjust_quantity_precision(quantity, symbol))  # Precision adjustment

    # Update the open trades dictionary
    open_trades[symbol]["remaining_quantity"] -= quantity
    if open_trades[symbol]["remaining_quantity"] <= 0:
        del open_trades[symbol]

    # Check stop loss based on ROE
    roe = calculate_roe(symbol)
    if roe is not None and roe < -2:
        print("Stop loss reached. Closing the trade.")
        # Close 100% of the trade
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=Client.ORDER_TYPE_MARKET,
            quantity=adjust_quantity_precision(quantity, symbol))  # Precision adjustment

        # Update the open trades dictionary
        open_trades[symbol]["remaining_quantity"] -= quantity
        if open_trades[symbol]["remaining_quantity"] <= 0:
            del open_trades[symbol]

        return order

    # Send a market order to close the trade with the specified quantity
    order = client.futures_create_order(
        symbol=symbol,
        side=side,
        type=Client.ORDER_TYPE_MARKET,
        quantity=adjust_quantity_precision(quantity, symbol))  # Precision adjustment

    # Update the open trades dictionary
    open_trades[symbol]["remaining_quantity"] -= quantity
    if open_trades[symbol]["remaining_quantity"] <= 0:
        del open_trades[symbol]

    return order


# Function to calculate ROE from Binance
def calculate_roe(symbol):
    try:
        # Fetch the current position's information
        position_info = client.futures_position_information(symbol=symbol)

        if position_info:
            position = position_info[0]
            unrealized_profit = float(position["unRealizedProfit"])
            entry_price = float(position["entryPrice"])
            position_amt = float(position["positionAmt"])
            leverage = float(position["leverage"])

            if entry_price != 0 and leverage != 0:
                roe = (unrealized_profit / ((entry_price * position_amt) / leverage)) * 100
                return roe

    except BinanceAPIException as e:

        print("Binance API Exception:", e)

    return None


def detect_signals():
    # Define the ROI coordinates (left, top, width, height)
    roi = (713, 90, 38, 700)

    # Define the reference signals
    ref_signal_long = cv2.imread('1.png')
    ref_signal_smalllong = cv2.imread('2.png')
    ref_signal_smallshort = cv2.imread('4.png')
    ref_signal_short = cv2.imread('signal-short.png')
    threshold = 0.8
    # Initialize the count of detection for each signal
    detection_count = {'long': 0, 'smalllong': 0, 'short': 0, 'smallshort': 0}

    # Initialize the number of screenshots
    num_screenshots = 2

    while True:
        try:
            for ref_signal, action in [
                (ref_signal_long, 'long'),
                (ref_signal_smalllong, 'smalllong'),
                (ref_signal_short, 'short'),
                (ref_signal_smallshort, 'smallshort'),
            ]:
                for _ in range(num_screenshots):
                    screenshot = pyautogui.screenshot(region=roi)
                    screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                    res = cv2.matchTemplate(screenshot, ref_signal, cv2.TM_CCOEFF_NORMED)
                    loc = np.where(res >= threshold)
                    cv2.imshow("Detected Signals", screenshot)
                    cv2.waitKey(1)
                    if len(loc[0]) > 0:
                        detection_count[action] += 1
                    time.sleep(0.3)  # Wait for 1 second

                if detection_count[action] == num_screenshots:
                    if action in ['long', 'smalllong']:
                        buy('BTCBUSD', 1)
                        print("Found a buy signal")
                    else:
                        sell('BTCBUSD', 1)
                        print("Found a sell signal")
                    time.sleep(2000)
                # Reset the count for the next iteration
                detection_count[action] = 0

            

        except KeyboardInterrupt:
            cv2.destroyAllWindows()
            break

if __name__ == "__main__":
    thread_ds = threading.Thread(target=detect_signals)
    thread_ds.start()

