"""Exceptions for aio_dahua_h5a."""


class DahuaH5AError(Exception):
    """Base exception for Dahua H5A client errors."""


class DahuaConnectionError(DahuaH5AError):
    """Raised when TCP connection or socket I/O to Port 37777 fails."""


class DahuaAuthError(DahuaH5AError):
    """Raised when DVR2 0xa0 digest authentication fails."""

    def __init__(self, message: str, error_code: int | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class DahuaRpcError(DahuaH5AError):
    """Raised when a 0xf6 JSON-RPC call returns result=false."""

    def __init__(self, method: str, error: object, response: dict | None = None) -> None:
        super().__init__(f"RPC method '{method}' failed: {error}")
        self.method = method
        self.error = error
        self.response = response
