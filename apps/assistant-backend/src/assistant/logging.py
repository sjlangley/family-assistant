import logging
import logging.config

from assistant.settings import settings

LOG_LEVEL = settings.log_level.upper()


LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        },
    },
    'handlers': {
        'default': {
            'formatter': 'standard',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
        },
    },
    'loggers': {
        # Use 'propagate': True and remove 'handlers' from children
        # to follow the "Root-Only" strategy discussed earlier.
        'uvicorn': {'level': LOG_LEVEL, 'propagate': True},
        'uvicorn.access': {'level': LOG_LEVEL, 'propagate': True},
        'fastapi': {'level': LOG_LEVEL, 'propagate': True},
        'assistant': {'level': LOG_LEVEL, 'propagate': True},
    },
    'root': {
        'handlers': ['default'],
        'level': LOG_LEVEL,
    },
}


def setup_logging():
    logging.config.dictConfig(LOGGING_CONFIG)
