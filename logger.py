import logging
import os
import sys


class LoggerFactory:
    _configured = False # ensures one-time global config

    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        """
        Returns a logger configured for STDOUT only.
        Also unifies Werkzeug logs with the same formatter.
        """

        logger = logging.getLogger(name)

        # Prevent duplicate handlers
        if logger.handlers:
            return logger

        log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)

        logger.setLevel(log_level)

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | "
            "%(filename)s:%(lineno)d | %(message)s"
        )
        handler.setFormatter(formatter)

        logger.addHandler(handler)
        logger.propagate = False

        # Configure Werkzeug logger ONCE
        if not LoggerFactory._configured:
            LoggerFactory._configure_werkzeug(handler, log_level)
            LoggerFactory._configured = True

        return logger

    @staticmethod
    def _configure_werkzeug(handler, log_level):
        werkzeug_logger = logging.getLogger("werkzeug")

        # Remove default Werkzeug handlers
        werkzeug_logger.handlers.clear()

        werkzeug_logger.setLevel(log_level)
        werkzeug_logger.addHandler(handler)
        werkzeug_logger.propagate = False