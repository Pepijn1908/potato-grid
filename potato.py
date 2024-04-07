import ccxt
import time
import sys
import logging
import json
import os

import keys  # import API key and secret key
from config import Config  # import configuration values

# set up logging
logging.basicConfig(level=logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler(Config.LOG_FILE)
file_handler.setFormatter(formatter)
logger = logging.getLogger()
logger.addHandler(file_handler)

# create a Binance exchange object using the API and secret keys
exchange = ccxt.deribit({
    'apiKey': keys.API_KEY,
    'secret': keys.SECRET_KEY
})

# use the Binance testnet
exchange.set_sandbox_mode(False)

# get the latest ticker information for the trading symbol
ticker = exchange.fetch_ticker(Config.SYMBOL)

# lists to store the orders
buy_orders = []
sell_orders = []
initial_balance = None

# function to write the current order data to a JSON file
def write_order_log(new_data, side):
    # Attempt to read the existing data first
    try:
        with open(Config.ORDER_LOG, 'r') as file:
            file_data = json.load(file)
    except (ValueError, FileNotFoundError):
        # If the file is empty, not found, or contains invalid JSON, start with empty lists
        file_data = {'buy': [], 'sell': []}

    # Update the relevant list with the new data
    file_data[side] = new_data

    # Open the file in write mode to overwrite with updated order data
    # This eliminates the possibility of leftover data from previous writes
    with open(Config.ORDER_LOG, 'w') as file:
        json.dump(file_data, file, indent=4)  # Using indent for better readability of the JSON file

# function to create a limit buy order at the given price
def create_buy_order(symbol, size, price):
    logger.info("==> submitting market limit buy order at {}".format(price))
    order = exchange.create_limit_buy_order(symbol, size, price)
    buy_orders.append(order['info'])

# function to create a limit sell order at the given price
def create_sell_order(symbol, size, price):
    logger.info("==> submitting market limit sell order at {}".format(price))
    order = exchange.create_limit_sell_order(symbol, size, price)
    sell_orders.append(order['info'])

# function to read order data from the file (if it exists) and populate the buy_orders and sell_orders lists
def init():
    global buy_orders, sell_orders

    if os.path.exists(Config.ORDER_LOG):
        with open(Config.ORDER_LOG, 'r+') as file:
            file_data = json.load(file)
            buy_orders = file_data['buy']
            sell_orders = file_data['sell']
    else:
        # if the file doesn't exist, create an empty one
        open(Config.ORDER_LOG, 'a').close()

def main():
    logger.info('=> Starting grid trading bot')
    initial_balance = exchange.fetch_balance()
    logger.info(f"=> BALANCE: {initial_balance} USDT")

    global buy_orders, sell_orders

    while True:
        # Fetch the latest ticker information to recalculate the mid-price
        ticker = exchange.fetch_ticker(Config.SYMBOL)
        mid_price = 1#(ticker['bid'] + ticker['ask']) / 2
        logger.info(f"Mid Price: {mid_price}")

        # Adjust buy and sell orders based on the new mid-price
        adjust_orders(mid_price)

        closed_order_ids = []

        # Check if buy order is closed
        for buy_order in buy_orders:
            logger.info("=> checking buy order {}".format(buy_order['order_id']))
            try:
                order = exchange.fetch_order(buy_order['order_id'], Config.SYMBOL)
            except Exception as e:
                logger.error(e)
                logger.warning("=> request failed, retrying")
                continue
                
            order_info = order['info']

            if order_info['order_state'] == Config.FILLED_ORDER_STATUS:
                closed_order_ids.append(order_info['order_id'])
                logger.info("=> buy order executed at {}".format(order_info['price']))
                new_sell_price = float(order_info['price']) + Config.GRID_STEP_SIZE
                if new_sell_price > mid_price:
                    create_sell_order(Config.SYMBOL, Config.POSITION_SIZE, new_sell_price)

        # Check if sell order is closed
        for sell_order in sell_orders:
            logger.info("=> checking sell order {}".format(sell_order['order_id']))
            try:
                order = exchange.fetch_order(sell_order['order_id'], Config.SYMBOL)
            except Exception as e:
                logger.error(e)
                logger.warning("=> request failed, retrying")
                continue
                
            order_info = order['info']

            if order_info['order_state'] == Config.FILLED_ORDER_STATUS:
                closed_order_ids.append(order_info['order_id'])
                logger.info("=> sell order executed at {}".format(order_info['price']))
                new_buy_price = float(order_info['price']) - Config.GRID_STEP_SIZE
                if new_buy_price < mid_price:
                    create_buy_order(Config.SYMBOL, Config.POSITION_SIZE, new_buy_price)

        # Remove closed orders from the list
        buy_orders = [buy_order for buy_order in buy_orders if buy_order['order_id'] not in closed_order_ids]
        sell_orders = [sell_order for sell_order in sell_orders if sell_order['order_id'] not in closed_order_ids]
        
        if closed_order_ids:
            # Write updated order logs to file
            write_order_log(buy_orders, 'buy')
            write_order_log(sell_orders, 'sell')

        # Exit if no sell orders are left
        if len(sell_orders) == 0:
            # Cancel all open buy orders
            exchange.cancel_all_orders(Config.SYMBOL)
            
            logger.info(f"=> Initial BALANCE: {initial_balance} USDT")
            logger.info(f"=> Final BALANCE: {exchange.fetch_balance()} USDT")
            
            sys.exit("Stopping bot, nothing left to sell")

        time.sleep(Config.CHECK_ORDERS_FREQUENCY)

def adjust_orders(mid_price):
    global buy_orders, sell_orders

    # Fetch the latest ticker information to get current bid and ask prices
    ticker = exchange.fetch_ticker(Config.SYMBOL)
    current_bid = ticker['bid']
    current_ask = ticker['ask']

    # Adjust buy orders: place below the current bid and mid_price
    for i in range(Config.NUM_BUY_GRID_LINES):
        price = mid_price - (Config.GRID_STEP_SIZE * (i + 1))
        if price < current_bid and not any(order for order in buy_orders if float(order['price']) == price):
            create_buy_order(Config.SYMBOL, Config.POSITION_SIZE, price)

    # Adjust sell orders: place above the current ask and mid_price
    for i in range(Config.NUM_SELL_GRID_LINES):
        price = mid_price + (Config.GRID_STEP_SIZE * (i + 1))
        if price > current_ask and not any(order for order in sell_orders if float(order['price']) == price):
            create_sell_order(Config.SYMBOL, Config.POSITION_SIZE, price)

    # Optionally, implement logic to cancel orders that are no longer correctly positioned
    # This might involve checking the current list of orders and comparing their prices against the current bid/ask

if __name__ == "__main__":
    init()
    main()