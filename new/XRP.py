import cv2
import numpy as np
from PIL import ImageGrab
import pytesseract
import time
from binance.client import Client
from binance.exceptions import BinanceAPIException
import traceback
import threading
import queue
api_key = 'ba32rkTiq8jWnGsnTu2U6wzFZpaR5koBknDKDv9Roes2L04jDEaiKax3Ru52onfr'
api_secret = 'F6W6DsWhkaw3O5IU8VkQHu2Xn2yGjAzfOS2qNiMtRRolBFvQ5kJsU45ogWaz0qwh'




client = Client(api_key, api_secret)

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
        client.futures_change_leverage(symbol=symbol, leverage=45)
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

        client.futures_change_leverage(symbol=symbol, leverage=45)
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

    # Double check the remaining quantity just before placing the market order
    update_open_trades()
    if symbol not in open_trades:
        print("No open position found.")
        return None
    real_remaining_quantity = abs(open_trades[symbol]["remaining_quantity"])

    # Adjust the quantity if necessary
    if real_remaining_quantity < quantity:
        print("Adjusting quantity to match the real remaining quantity.")
        quantity = real_remaining_quantity

    # Determine the side (buy/sell) based on the position_type
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

    return order

def stop_loss(symbol, position_type):
    # Update the open trades dictionary
    update_open_trades()

    # If no open position, return None
    if symbol not in open_trades:
        print("No open position found.")
        return None

    # Calculate the quantity to close (100% of the position)
    quantity = abs(open_trades[symbol]["remaining_quantity"])

    # Determine the side (buy/sell) based on the position_type
    side = Client.SIDE_BUY if position_type == "short" else Client.SIDE_SELL

    # Send a market order to close the trade with the specified quantity
    order = client.futures_create_order(
        symbol=symbol,
        side=side,
        type=Client.ORDER_TYPE_MARKET,
        quantity=adjust_quantity_precision(quantity, symbol))  # Precision adjustment

    # Update the open trades dictionary
    if symbol in open_trades:
        del open_trades[symbol]

    return order
profit_stop_loss_queue = queue.Queue()

def profit_stop_loss_short(symbol, initial_pnl, queue):
    while True:
        if not queue.empty():  # If there is a message in the queue, break the loop
            break
        try:
            current_pnl = calculate_pnl(symbol)
            print(f"profit PNL for {symbol}: {current_pnl}")  # Print the current PNL
            if initial_pnl - current_pnl >= 20:  # If the PNL drops by 10 or more
                print(
                    f"Profit 1 stop loss hit. PNL dropped by 10 or more. Current PNL for {symbol}: {current_pnl}. Closing the trade.")
                # Close 100% of the trade
                stop_loss(symbol, "short")
                break
        except Exception as e:
            print("An error occurred:", str(e))
            traceback.print_exc()  # This will print the full traceback of the error
        time.sleep(1)
# Function to calculate ROE from Binance
def profit_stop_loss_long(symbol, initial_pnl, queue):
    while True:
        if not queue.empty():  # If there is a message in the queue, break the loop
            break
        try:
            current_pnl = calculate_pnl(symbol)
            print(f"profit PNL for {symbol}: {current_pnl}")  # Print the current PNL
            if initial_pnl - current_pnl >= 20:  # If the PNL drops by 10 or more
                print(
                    f"Profit 1 stop loss hit. PNL dropped by 10 or more. Current PNL for {symbol}: {current_pnl}. Closing the trade.")
                # Close 100% of the trade
                stop_loss(symbol, "long")
                break
        except Exception as e:
            print("An error occurred:", str(e))
            traceback.print_exc()  # This will print the full traceback of the error
        time.sleep(1)
# Function to calculate ROE from Binance
def calculate_pnl(symbol):
    try:
        # Fetch the current position's information
        position_info = client.futures_position_information(symbol=symbol)

        if position_info:
            position = next(filter(lambda p: p['symbol'] == symbol, position_info), None)
            if position:
                unrealized_pnl = float(position["unRealizedProfit"])
                return unrealized_pnl

    except BinanceAPIException as e:
        print(e)

    return None




# Your other code for screen capture, OCR, and trade execution based on text signal should follow here...
def capture_screen(bbox=None):
    cap_screen = np.array(ImageGrab.grab(bbox))
    image = process_img(cap_screen)
    cv2.imshow("Detected Signals", image)
    cv2.waitKey(1)
    return image


# Function to process the image
def process_img(image):
    image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'  # Update this path accordingly

previous_text = None
while True:
    left = 365
    top = 970
    width = 475
    height = 20

    screen = capture_screen(bbox=(left, top, left + width, top + height))
    text = pytesseract.image_to_string(screen)

    text = text.replace(' ', '')

    print(text)
    update_open_trades()
    for symbol in list(open_trades.keys()):  # Create a copy of keys with list()
        if symbol == 'XRPBUSD':
            pnl = calculate_pnl(symbol)
            if pnl is not None:
                print(f"Current PNL for {symbol}: {pnl}")  # Print the current PNL
                if pnl < -150:  # Trigger stop loss if PNL is less than -$100
                    print(f"Stop loss reached for {symbol}. PNL is {pnl}. Closing the trade.")
                    # Close 100% of the trade
                    position_type = "short" if open_trades[symbol]["remaining_quantity"] < 0 else "long"
                    stop_loss(symbol, position_type)

    if previous_text is not None and text.strip() != previous_text:
        print("Change detected")
        if text.strip() == "Alert:ShortSignalonXRPUSD" or text.strip() == "Alert:StrongShortSignalonXRPUSD":
            print("Take profit 1 reached for short")
            # Close 75% of the trade
            sell('XRPBUSD', 49500, "short")
        elif text.strip() == "Alert:LongSignalonXRPUSD" or text.strip() == "Alert:StrongLongSignalonXRPUSD":
            print("Take profit 1 reached for short")
            # Close 75% of the trade
            buy('XRPBUSD', 49500, "long")




        elif text.strip() == "Alert:ShortTakeProfit1onXRPUSD":
             print("Take profit 1 reached for short")
                    # Close 75% of the trade
             take_profit('XRPBUSD', 0.75, "short")
             initial_pnl = calculate_pnl(symbol)
             print(f"int PNL for {symbol}: {initial_pnl}")
                    # Start the profit stop loss function in a separate thread and pass the queue as an argument
             threading.Thread(target=profit_stop_loss_short,args=(symbol, initial_pnl, profit_stop_loss_queue)).start()


        elif text.strip() == "Alert:LongTakeProfit1onXRPUSD":
            print("Take profit 1 reached for long")
            # Close 75% of the trade
            take_profit('XRPBUSD', 0.75, "long")
            initial_pnl = calculate_pnl(symbol)
            print(f"int PNL for {symbol}: {initial_pnl}")
            # Start the profit stop loss function in a separate thread and pass the queue as an argument
            threading.Thread(target=profit_stop_loss_long, args=(symbol, initial_pnl, profit_stop_loss_queue)).start()

        elif text.strip() == "Alert:ShortTakeProfit2onXRPUSD":
            print("Take profit 2 reached for short")
            # Close 100% of the trade
            take_profit('XRPBUSD', 1, "short")

        elif text.strip() == "Alert:LongTakeProfit2onXRPUSD":
            print("Take profit 2 reached for long")
            # Close 100% of the trade
            take_profit('XRPBUSD', 1, "long")

        elif text.strip() == "Alert:LongStopLossonXRPUSD" or text.strip() == "Alert:LongExitonXRPUSD":
            print("long stop loss")
            # Close 100% of the trade
            take_profit('XRPBUSD', 1, "long")

        elif text.strip() == "Alert:ShortStopLossonXRPUSD" or text.strip() == "Alert:ShortExitonXRPUSD":
            print("short stop loss")
            # Close 100% of the trade
            take_profit('XRPBUSD', 1, "short")

        else:
            print("Unknown signal detected: " + text)

    previous_text = text.strip()
    time.sleep(1)  # Adjust the sleep time as needed