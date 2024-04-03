# Define the Config class to store the bot's settings
class Config:
    # Define the default symbol and position size
    SYMBOL = "USDC/USDT"
    POSITION_SIZE = 10

    # Define the number of grid lines to use for buying and selling
    NUM_BUY_GRID_LINES = 5
    NUM_SELL_GRID_LINES = 5

    # Define the size of each grid step
    GRID_STEP_SIZE = 0.0001

    # Define the frequency at which to check for filled orders and the order status to look for
    CHECK_ORDERS_FREQUENCY = 1
    FILLED_ORDER_STATUS = 'filled'

    # Define the log file to use for logging trading information
    LOG_FILE = 'trading.log'

    # Define the file to use for storing placed orders
    ORDER_LOG = 'orders.json'