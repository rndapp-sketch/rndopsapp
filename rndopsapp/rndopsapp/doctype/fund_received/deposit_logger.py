# Copyright (c) 2025, rndops and contributors
# Deposit Slip Logger - Centralized logging for Deposit Slip creation from Fund Received

import os
import logging
import traceback
from datetime import datetime
from typing import Optional, Any
from logging.handlers import RotatingFileHandler

# --- LOG DIRECTORY CONFIGURATION ---
LOG_DIR = os.path.dirname(os.path.abspath(__file__))

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# --- LOG FILE PATHS ---
DEPOSIT_LOG_FILE = os.path.join(LOG_DIR, 'deposit.log')
ERROR_LOG_FILE = os.path.join(LOG_DIR, 'error.log')

# --- LOG FORMAT ---
LOG_FORMAT = '%(asctime)s | %(levelname)s | %(name)s | %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# --- LOG ROTATION SETTINGS ---
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5  # Keep 5 backup files


class DepositLogger:
    """
    Centralized logging class for Deposit Slip operations.
    Provides separate loggers for deposits and errors.
    """

    _deposit_logger: Optional[logging.Logger] = None
    _error_logger: Optional[logging.Logger] = None

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
    def get_deposit_logger(cls) -> logging.Logger:
        """Get the deposit logger instance."""
        if cls._deposit_logger is None:
            cls._deposit_logger = cls._create_logger(
                'deposit.slip',
                DEPOSIT_LOG_FILE,
                logging.INFO
            )
        return cls._deposit_logger

    @classmethod
    def get_error_logger(cls) -> logging.Logger:
        """Get the error logger instance."""
        if cls._error_logger is None:
            cls._error_logger = cls._create_logger(
                'deposit.error',
                ERROR_LOG_FILE,
                logging.ERROR
            )
        return cls._error_logger


# --- CONVENIENCE FUNCTIONS ---

def get_deposit_logger() -> logging.Logger:
    """Get the deposit logger instance."""
    return DepositLogger.get_deposit_logger()


def get_error_logger() -> logging.Logger:
    """Get the error logger instance."""
    return DepositLogger.get_error_logger()


def log_deposit_creation(
    fund_received_name: str,
    deposit_slip_name: str,
    deposit_doctype: str,
    data: Optional[dict] = None,
    category: str = ""
):
    """
    Log successful deposit slip creation.

    Args:
        fund_received_name: Name of the Fund Received document
        deposit_slip_name: Name of the created Deposit Slip document
        deposit_doctype: Type of Deposit Slip created
        data: Data used to create the deposit slip
        category: Category used for doctype selection
    """
    logger = get_deposit_logger()
    data_keys = list(data.keys()) if isinstance(data, dict) else []
    
    log_msg = (
        f"[DEPOSIT_CREATED] [SUCCESS] "
        f"fund_received={fund_received_name} | "
        f"deposit_slip={deposit_slip_name} | "
        f"doctype={deposit_doctype} | "
        f"category={category} | "
        f"data_keys={data_keys}"
    )
    logger.info(log_msg)


def log_deposit_link(
    fund_received_name: str,
    deposit_slip_name: str,
    deposit_doctype: str
):
    """
    Log the linking of Deposit Slip to Fund Received.

    Args:
        fund_received_name: Name of the Fund Received document
        deposit_slip_name: Name of the Deposit Slip document
        deposit_doctype: Type of Deposit Slip
    """
    logger = get_deposit_logger()
    
    log_msg = (
        f"[DEPOSIT_LINKED] [SUCCESS] "
        f"fund_received={fund_received_name} -> "
        f"deposit_slip={deposit_slip_name} | "
        f"doctype={deposit_doctype}"
    )
    logger.info(log_msg)


def log_deposit_error(
    fund_received_name: str,
    error_message: str,
    data: Optional[dict] = None,
    traceback_str: Optional[str] = None,
    error_type: str = "DEPOSIT_ERROR"
):
    """
    Log deposit slip creation errors.

    Args:
        fund_received_name: Name of the Fund Received document
        error_message: Error message
        data: Data that was being processed
        traceback_str: Full traceback string
        error_type: Type of error for categorization
    """
    error_logger = get_error_logger()
    deposit_logger = get_deposit_logger()
    
    data_keys = list(data.keys()) if isinstance(data, dict) else []
    
    # Main error message
    error_log_msg = (
        f"[{error_type}] [FAILED] "
        f"fund_received={fund_received_name} | "
        f"error={error_message} | "
        f"data_keys={data_keys}"
    )
    
    # Log to both error log and deposit log
    error_logger.error(error_log_msg)
    deposit_logger.error(error_log_msg)
    
    # Log full traceback separately for debugging
    if traceback_str:
        tb_msg = (
            f"[{error_type}] [TRACEBACK] "
            f"fund_received={fund_received_name}\n"
            f"{traceback_str}"
        )
        error_logger.error(tb_msg)


def log_category_inference(
    fund_received_name: str,
    project_title: Optional[str],
    project_type: Optional[str],
    inferred_category: str
):
    """
    Log category inference process.

    Args:
        fund_received_name: Name of the Fund Received document
        project_title: Project title/number
        project_type: Project type from registration
        inferred_category: Category that was inferred
    """
    logger = get_deposit_logger()
    
    log_msg = (
        f"[CATEGORY_INFERRED] [INFO] "
        f"fund_received={fund_received_name} | "
        f"project={project_title} | "
        f"project_type={project_type} | "
        f"inferred_category={inferred_category}"
    )
    logger.info(log_msg)


def log_workflow_state(
    fund_received_name: str,
    deposit_slip_name: str,
    workflow_state: str
):
    """
    Log workflow state assignment.

    Args:
        fund_received_name: Name of the Fund Received document
        deposit_slip_name: Name of the Deposit Slip document
        workflow_state: Assigned workflow state
    """
    logger = get_deposit_logger()
    
    log_msg = (
        f"[WORKFLOW_STATE] [INFO] "
        f"fund_received={fund_received_name} | "
        f"deposit_slip={deposit_slip_name} | "
        f"state={workflow_state}"
    )
    logger.info(log_msg)


def log_deposit_event(
    event_type: str,
    fund_received_name: str,
    status: str,
    message: str = "",
    deposit_slip_name: str = "",
    extra: Optional[dict] = None
):
    """
    Log a generic deposit event with structured format.

    Args:
        event_type: Type of event (e.g., DEPOSIT_CREATED, DEPOSIT_APPROVAL)
        fund_received_name: Fund Received document name
        status: Status (SUCCESS, FAILED, WARNING, etc.)
        message: Additional message
        deposit_slip_name: Deposit Slip document name
        extra: Additional data to log
    """
    logger = get_deposit_logger()
    
    log_msg = f"[{event_type}] [{status}] fund_received={fund_received_name}"
    
    if deposit_slip_name:
        log_msg += f" | deposit_slip={deposit_slip_name}"
    if message:
        log_msg += f" | {message}"
    if extra:
        log_msg += f" | extra={extra}"

    if status in ['FAILED', 'ERROR']:
        logger.error(log_msg)
        get_error_logger().error(log_msg)
    elif status == 'WARNING':
        logger.warning(log_msg)
    else:
        logger.info(log_msg)


def log_error(
    message: str,
    error_type: str = "DEPOSIT_ERROR",
    exc_info: bool = False
):
    """
    Log a general error message.

    Args:
        message: Error message
        error_type: Type of error for categorization
        exc_info: Whether to include exception info
    """
    logger = get_error_logger()
    logger.error(f"[{error_type}] {message}", exc_info=exc_info)


def log_info(message: str):
    """
    Log an info message.

    Args:
        message: Info message
    """
    get_deposit_logger().info(message)


def log_warning(message: str):
    """
    Log a warning message.

    Args:
        message: Warning message
    """
    get_deposit_logger().warning(message)
