import logging

def get_logger(name: str) -> logging.Logger:
    """
    Standardized logger factory for the KapuLetu Backend.
    
    Ensures that loggers are configured consistently across all Lambda functions,
    using a stream handler that integrates with AWS CloudWatch.
    
    Args:
        name (str): The name of the module (typically __name__).
        
    Returns:
        logging.Logger: A configured logger instance.
    """
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers in persistent Lambda execution environments
    if not logger.handlers:
        handler = logging.StreamHandler()
        # Format: timestamp - module - level - message
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        # Default log level is INFO; can be changed via environment variables if needed
        logger.setLevel(logging.INFO)
        
    return logger
