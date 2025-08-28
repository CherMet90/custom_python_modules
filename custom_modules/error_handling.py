from custom_modules.error_aggregator import ErrorAggregator
from custom_modules.log import logger

AGG = ErrorAggregator()  # Singleton

def print_errors():
    logger.info('The work is completed')

    AGG.render()