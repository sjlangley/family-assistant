import logging
import logging.config

from assistant.settings import settings


def setup_logging():
    log_level = settings.log_level.upper()
    logging_config = {
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
            'uvicorn': {'level': log_level, 'propagate': True},
            'uvicorn.access': {'level': log_level, 'propagate': True},
            'fastapi': {'level': log_level, 'propagate': True},
            'assistant': {'level': log_level, 'propagate': True},
        },
        'root': {
            'handlers': ['default'],
            'level': log_level,
        },
    }

    logging.config.dictConfig(logging_config)
