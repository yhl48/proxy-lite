import asyncio
import logging
import sys
import time  # Added for time.sleep
from typing import Literal
from uuid import uuid4

from rich.logging import RichHandler


class StructuredLogger(logging.Logger):
    def _stream_message_sync(self, message: str) -> None:
        """Synchronous version of stream message to run in separate thread."""
        try:
            sys.stdout.write("\r")  # Overwrite current line
            for char in message:
                sys.stdout.write(char)
                sys.stdout.flush()
                time.sleep(0.002)  # Using regular sleep in thread
            sys.stdout.write("\n")
        except Exception:
            pass

    async def stream_message(self, message: str) -> None:
        """Streams the message character by character in a separate thread."""
        return await asyncio.to_thread(self._stream_message_sync, message)

    # def info_stream(self, msg: str) -> Coroutine[Any, Any, None]:
    #     """Special method for streaming messages that returns a coroutine."""
    #     # Log the message normally first
    #     # self.info(msg)
    #     # Return the streaming coroutine
    #     return self.stream_message(msg)

    def _log(
        self,
        level,
        msg,
        args,
        exc_info=None,
        extra=None,
        stack_info=False,
        stacklevel=1,
    ):
        if extra is None:
            extra = {}

        json_fields = {
            "logger_name": self.name,
            "message": msg % args if args else msg,
        }

        exc_type, exc_value, exc_traceback = sys.exc_info()
        if exc_type is not None:
            json_fields["exception_class"] = exc_type.__name__
            json_fields["exception_message"] = str(exc_value)

        json_fields.update(extra)

        super()._log(
            level,
            msg,
            args,
            exc_info,
            {"json_fields": json_fields},
            stack_info,
            stacklevel + 1,
        )


def create_logger(
    name: str,
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
    detailed_name: bool = False,
) -> logging.Logger:
    unique_name = f"{name}-{str(uuid4())[:8]}"
    logger = logging.getLogger(unique_name)
    logger.setLevel(level)

    # Standard RichHandler for structured logs
    rich_handler = RichHandler(
        rich_tracebacks=True,
        markup=True,
        show_path=False,
        show_time=False,
        log_time_format="[%s]",
    )

    if detailed_name:
        rich_handler.setFormatter(logging.Formatter("%(name)s:\n%(message)s"))
    else:
        rich_handler.setFormatter(logging.Formatter("-----\n%(message)s"))

    logger.addHandler(rich_handler)
    logger.propagate = False

    return logger


# Set StructuredLogger as the default logger class
logging.setLoggerClass(StructuredLogger)

# Initialize logger
logger = create_logger(__name__, level="INFO")

stream_logger = create_logger(__name__, level="INFO", detailed_name=False)
