# Copyright (c) 2025, rndops and contributors
# Kafka Logger - Centralized logging infrastructure for Kafka operations

import os
import logging
from datetime import datetime
from typing import Optional
from logging.handlers import RotatingFileHandler

# --- LOG DIRECTORY CONFIGURATION ---
# Default log directory: kafka/logs/files/
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'files')

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# --- LOG FILE PATHS ---
PRODUCER_LOG_FILE = os.path.join(LOG_DIR, 'producer.log')
CONSUMER_LOG_FILE = os.path.join(LOG_DIR, 'consumer.log')
ERROR_LOG_FILE = os.path.join(LOG_DIR, 'error.log')
DEBUG_LOG_FILE = os.path.join(LOG_DIR, 'debug.log')

# --- LOG FORMAT ---
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# --- LOG ROTATION SETTINGS ---
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5  # Keep 5 backup files


class KafkaLogger:
    """
    Centralized logging class for Kafka operations.
    Provides separate loggers for producers, consumers, and errors.
    """

    _producer_logger: Optional[logging.Logger] = None
    _consumer_logger: Optional[logging.Logger] = None
    _error_logger: Optional[logging.Logger] = None
    _debug_logger: Optional[logging.Logger] = None

    @classmethod
    def _create_logger(cls, name: str, log_file: str, level: int = logging.INFO) -> logging.Logger:
        """
        Create a logger with rotating file handler.

        Args:
            name: Logger name
            log_file: Path to log file
            level: Logging level

        Returns:
            logging.Logger: Configured logger instance
        """
        logger = logging.getLogger(name)
        logger.setLevel(level)

        # Prevent duplicate handlers
        if not logger.handlers:
            # File handler with rotation
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=MAX_BYTES,
                backupCount=BACKUP_COUNT
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
            logger.addHandler(file_handler)

            # Console handler for debugging
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
            logger.addHandler(console_handler)

        return logger

    @classmethod
    def get_producer_logger(cls) -> logging.Logger:
        """Get the producer logger instance."""
        if cls._producer_logger is None:
            cls._producer_logger = cls._create_logger(
                'kafka.producer',
                PRODUCER_LOG_FILE,
                logging.INFO
            )
        return cls._producer_logger

    @classmethod
    def get_consumer_logger(cls) -> logging.Logger:
        """Get the consumer logger instance."""
        if cls._consumer_logger is None:
            cls._consumer_logger = cls._create_logger(
                'kafka.consumer',
                CONSUMER_LOG_FILE,
                logging.INFO
            )
        return cls._consumer_logger

    @classmethod
    def get_error_logger(cls) -> logging.Logger:
        """Get the error logger instance."""
        if cls._error_logger is None:
            cls._error_logger = cls._create_logger(
                'kafka.error',
                ERROR_LOG_FILE,
                logging.ERROR
            )
        return cls._error_logger

    @classmethod
    def get_debug_logger(cls) -> logging.Logger:
        """Get the debug logger instance."""
        if cls._debug_logger is None:
            cls._debug_logger = cls._create_logger(
                'kafka.debug',
                DEBUG_LOG_FILE,
                logging.DEBUG
            )
        return cls._debug_logger


# --- CONVENIENCE FUNCTIONS ---

def get_producer_logger() -> logging.Logger:
    """Get the producer logger instance."""
    return KafkaLogger.get_producer_logger()


def get_consumer_logger() -> logging.Logger:
    """Get the consumer logger instance."""
    return KafkaLogger.get_consumer_logger()


def get_error_logger() -> logging.Logger:
    """Get the error logger instance."""
    return KafkaLogger.get_error_logger()


def log_producer_event(
    event_type: str,
    doc_name: str,
    topic: str,
    status: str,
    message: str = "",
    extra: Optional[dict] = None
):
    """
    Log a producer event with structured format.

    Args:
        event_type: Type of event (e.g., PROJECT_REGISTRATION, FUND_SANCTION)
        doc_name: Document name being processed
        topic: Kafka topic
        status: Status (SUCCESS, FAILED, RETRY, etc.)
        message: Additional message
        extra: Additional data to log
    """
    logger = get_producer_logger()
    log_msg = f"[{event_type}] [{status}] doc={doc_name} | topic={topic}"
    if message:
        log_msg += f" | {message}"
    if extra:
        log_msg += f" | extra={extra}"

    if status in ['FAILED', 'ERROR']:
        logger.error(log_msg)
        KafkaLogger.get_error_logger().error(log_msg)
    elif status == 'WARNING':
        logger.warning(log_msg)
    else:
        logger.info(log_msg)


def log_consumer_event(
    event_type: str,
    doc_name: str,
    topic: str,
    status: str,
    message: str = "",
    partition: Optional[int] = None,
    offset: Optional[int] = None,
    extra: Optional[dict] = None
):
    """
    Log a consumer event with structured format.

    Args:
        event_type: Type of event (e.g., FUND_RECEIVED_UPDATE, DEPOSIT_SLIP_UPDATE)
        doc_name: Document name being processed
        topic: Kafka topic
        status: Status (SUCCESS, FAILED, RETRY, etc.)
        message: Additional message
        partition: Kafka partition number
        offset: Kafka offset
        extra: Additional data to log
    """
    logger = get_consumer_logger()
    log_msg = f"[{event_type}] [{status}] doc={doc_name} | topic={topic}"
    if partition is not None:
        log_msg += f" | partition={partition}"
    if offset is not None:
        log_msg += f" | offset={offset}"
    if message:
        log_msg += f" | {message}"
    if extra:
        log_msg += f" | extra={extra}"

    if status in ['FAILED', 'ERROR']:
        logger.error(log_msg)
        KafkaLogger.get_error_logger().error(log_msg)
    elif status == 'WARNING':
        logger.warning(log_msg)
    else:
        logger.info(log_msg)


def log_error(message: str, error_type: str = "KAFKA_ERROR", exc_info: bool = False):
    """
    Log an error message.

    Args:
        message: Error message
        error_type: Type of error for categorization
        exc_info: Whether to include exception info
    """
    logger = KafkaLogger.get_error_logger()
    logger.error(f"[{error_type}] {message}", exc_info=exc_info)


def log_info(message: str, logger_type: str = "producer"):
    """
    Log an info message.

    Args:
        message: Info message
        logger_type: Which logger to use (producer/consumer)
    """
    if logger_type == "consumer":
        get_consumer_logger().info(message)
    else:
        get_producer_logger().info(message)


def log_warning(message: str, logger_type: str = "producer"):
    """
    Log a warning message.

    Args:
        message: Warning message
        logger_type: Which logger to use (producer/consumer)
    """
    if logger_type == "consumer":
        get_consumer_logger().warning(message)
    else:
        get_producer_logger().warning(message)


def log_debug(message: str):
    """
    Log a debug message.

    Args:
        message: Debug message
    """
    KafkaLogger.get_debug_logger().debug(message)
