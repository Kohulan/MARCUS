from fastapi import Request, status
from fastapi.responses import JSONResponse


class InvalidInputException(Exception):
    """Exception raised for invalid input."""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(self.detail)


async def input_exception_handler(request: Request, exc: InvalidInputException):
    """
    Handler for InvalidInputException.

    Args:
        request: The FastAPI request
        exc: The exception instance

    Returns:
        JSONResponse: A JSON response with the exception details
    """
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.detail},
    )
