import logging
import sys
from logging.handlers import RotatingFileHandler # file handler that rotates log files when they reach a certain size
import os

def setup_logging():
    """Sets up a production-grade logging system."""
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    log_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    
    # 1. Console Handler sends logs to terminal (for Docker logs/AWS CloudWatch) because these logs are not stored in files but collected from stdout
    console_handler = logging.StreamHandler(sys.stdout) #StreamHandler sends logs to a stream (like terminal, file-like object, etc.)
    console_handler.setFormatter(log_formatter) # applied the format we defined above
    
    # 2. File Handler (for local persistence) ie writes logs in files
    file_handler = RotatingFileHandler( #the handler rotates log files by renaming the current log file and opening a new empty file to continue logging if file size exceeds maxbytes, backupcount is the number of backup files to keep, when backupcount is reached, the oldest file in the sequence is deleted to make room for new files
        "logs/medvault.log", maxBytes=10*1024*1024, backupCount=5
    )
    file_handler.setFormatter(log_formatter) # applies the format we defined above
    
    # Root Logger Configuration
    root_logger = logging.getLogger() #get the root logger
    root_logger.setLevel(logging.INFO) # only logs with level INFO or higher will be shown heirarchy is DEBUG, INFO, WARNING, ERROR, CRITICAL
    root_logger.addHandler(console_handler) # logs will be displayed in terminal
    root_logger.addHandler(file_handler) # logs will be written in files
    
    # Set levels for specific third-party loggers to reduce noise
    logging.getLogger("uvicorn").setLevel(logging.INFO) # uvicorn server logs are set to info 
    logging.getLogger("httpx").setLevel(logging.WARNING) # http requests logs are set to warning 
    logging.getLogger("docling").setLevel(logging.INFO) # document processing logs are set to info 

    logging.info("MedVault logging initialized.")

logger = logging.getLogger("medvault")
