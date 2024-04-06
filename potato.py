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

# main trading logic
def main():
    logger.info('=> Starting grid trading bot')
    initial_balance = exchange.fetch_balance()
    logger.info(f"=> BALANCE: {initial_balance} USDT")

    global buy_orders, sell_orders
    
    # Calculate the mid-price as the average of the bid and ask prices
    mid_price = 1.0 #(ticker['bid'] + ticker['ask']) / 2
    logger.info(f"Mid Price: {mid_price}")
    
    if not buy_orders:
        # place initial buy orders based on mid_price
        grid_lines = range(Config.NUM_SELL_GRID_LINES)
        for i in grid_lines:
            price = mid_price - (Config.GRID_STEP_SIZE * (i + 1))
            if price < ticker['bid']:
                create_buy_order(Config.SYMBOL, Config.POSITION_SIZE, price)
            #else:
            #    grid_lines = grid_lines.stop + 1
        
        # write order logs to file
        write_order_log(buy_orders, 'buy')

        # place initial sell orders based on mid_price
        grid_lines = range(Config.NUM_SELL_GRID_LINES)
        for i in grid_lines:
            price = mid_price + (Config.GRID_STEP_SIZE * (i + 1))
            if price > ticker['ask']:
                create_sell_order(Config.SYMBOL, Config.POSITION_SIZE, price)
            #else:
            #    grid_lines.stop = grid_lines.stop + 1

        # write order logs to file
        write_order_log(sell_orders, 'sell')


    while True:
        closed_order_ids = []

        # check if buy order is closed
        for buy_order in buy_orders:
            #logger.info("=> checking buy order {}".format(buy_order['order_id']))
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
                # logger.info("=> creating new limit sell order at {}".format(new_sell_price))
                if new_sell_price > mid_price:
                    create_sell_order(Config.SYMBOL, Config.POSITION_SIZE, new_sell_price)

            time.sleep(Config.CHECK_ORDERS_FREQUENCY)

        # check if sell order is closed
        for sell_order in sell_orders:
            #logger.info("=> checking sell order {}".format(sell_order['order_id']))
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
                logger.info(f"=> BALANCE: {exchange.fetch_balance()} USDT")
                new_buy_price = float(order_info['price']) - Config.GRID_STEP_SIZE
                # logger.info("=> creating new limit buy order at {}".format(new_buy_price))
                if new_buy_price < mid_price:
                    create_buy_order(Config.SYMBOL, Config.POSITION_SIZE, new_buy_price)

            time.sleep(Config.CHECK_ORDERS_FREQUENCY)

        # remove closed orders from list
        buy_orders = [buy_order for buy_order in buy_orders if buy_order['order_id'] not in closed_order_ids]
        sell_orders = [sell_order for sell_order in sell_orders if sell_order['order_id'] not in closed_order_ids]
        
        if closed_order_ids:
            # write updated order logs to file
            write_order_log(buy_orders, 'buy')
            write_order_log(sell_orders, 'sell')

        # exit if no sell orders are left
        if len(sell_orders) == 0:
            # cancel all open buy orders
            exchange.cancel_all_orders(Config.SYMBOL)
            
            logger.info(f"=> Initial BALANCE: {initial_balance} USDT")
            logger.info(f"=> Final BALANCE: {exchange.fetch_balance()} USDT")
            
            sys.exit("stopping bot, nothing left to sell")

if __name__ == "__main__":
    init()
    main()