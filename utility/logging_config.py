import logging
import sys

os_platform = sys.platform


class NoNewlineStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            stream.write(msg)
            # Flush the stream but don't add a newline
            stream.flush()
        except Exception:
            self.handleError(record)


# Handle error messages for OS
def log_error(message, end='\n'):
    logger = setup_logger()
    if not os_platform == 'win32':
        logger.error(message, extra={'end': end})
    else:
        print(message, end=end)


def log_info(message, end='\n'):
    logger = setup_logger()
    if not os_platform == 'win32':
        logger.info(message, extra={'end': end})
    else:
        print(message, end=end)


def setup_logger(name='PalServer-Util'):
    # Set up logging
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Use the correct handler for the platform
    if not os_platform == 'win32':
        # Linux - systemd journal
        try:
            from systemd.journal import JournalHandler
            handler = JournalHandler()
        except ImportError:
            # Fall back to console in systemd not available
            handler = NoNewlineStreamHandler()
    else:
        # Windows - console log
        handler = NoNewlineStreamHandler()

    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    # Add handler to logger
    if not logger.handlers:
        logger.addHandler(handler)

    return logger
