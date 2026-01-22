"""Contains different utility functions."""
import logging
import os
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from dynaconf import Dynaconf


def get_settings() -> Dynaconf:
    """Create and return dynaconf setting object."""
    settings = Dynaconf(
        environments=True,
        settings_files=["settings.toml", ".secrets.toml"],
    )
    # Load environment variables from .env file
    load_dotenv()
    environment = os.getenv("DYNACONF_ENV")
    settings.setenv(environment)
    return settings


class ProcessFormatter(logging.Formatter):
    """Logger name formatter."""

    def format(self, record):
        return super().format(record)


def get_logger(settings: Dynaconf) -> logging.getLogger:
    """Create and return logger object."""
    # Create a logger instance
    logger = logging.getLogger("bot_logger")
    logger.setLevel(logging.INFO)

    # Check if any handlers are already attached to the logger
    if not logger.handlers:
        logs_path = settings.get("LOGS_PATH")
        # Create a file handler with log rotation based on file size
        # maxBytes = 10Mb, if you want to delete old file add backupCount=int
        handler = RotatingFileHandler(logs_path, maxBytes=1e7, encoding="utf-8")
        handler.setLevel(logging.INFO)

        # Create a formatter and set it on the handler
        formatter = ProcessFormatter(
            fmt="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)s - %(funcName)s - %(message)s",
            datefmt="%m-%d-%Y %H:%M:%S"  # Set the date format without milliseconds
        )

        handler.setFormatter(formatter)

        # Add the handler to the logger
        logger.addHandler(handler)

        # Create a stream handler to log messages to the console
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(formatter)

        # Add the stream handler to the logger
        logger.addHandler(stream_handler)

    return logger


def get_db_connection(settings: Dynaconf, logger: logging.Logger) -> str | None:

    """
    Returns a SQL Server connection based on Dynaconf settings.
    If USE_PRODUCTION_DB is True, uses production credentials;
    otherwise uses local trusted connection.
    """

    try:
        if settings.USE_PRODUCTION_DB:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={settings.DB_SERVER};"
                f"DATABASE={settings.DB_NAME};"
                f"UID={settings.USERNAME};"
                f"PWD={settings.PASSWORD};"
            )
        else:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={settings.DB_SERVER};"
                f"DATABASE={settings.DB_NAME};"
                f"Trusted_Connection=yes;"
                f"TrustServerCertificate=yes;"
            )

        # return pyodbc.connect(conn_str)
        return conn_str

    except Exception as e:
        logger.error(f"SQL Connection Error: {e}")
        return None

