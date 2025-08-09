"""Custom exceptions for QDash client."""

from typing import Any, Optional, Dict
import httpx


class QDashError(Exception):
    """Base exception for QDash client errors."""
    pass


class QDashHTTPError(QDashError):
    """HTTP error with detailed context for debugging and support."""
    
    def __init__(
        self,
        message: str,
        status_code: int,
        response_body: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        request_url: Optional[str] = None,
        request_id: Optional[str] = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.headers = headers or {}
        self.request_url = request_url
        self.request_id = request_id or headers.get('x-request-id') if headers else None
    
    def __str__(self) -> str:
        parts = [f"HTTP {self.status_code}: {super().__str__()}"]
        
        if self.request_url:
            parts.append(f"URL: {self.request_url}")
            
        if self.request_id:
            parts.append(f"Request ID: {self.request_id}")
            
        if self.response_body:
            # Safely truncate response body for display
            body_preview = self.response_body[:500]
            if len(self.response_body) > 500:
                body_preview += "... (truncated)"
            parts.append(f"Response: {body_preview}")
            
        return " | ".join(parts)


class QDashConnectionError(QDashError):
    """Network connection error."""
    pass


class QDashTimeoutError(QDashError):
    """Request timeout error."""
    pass


class QDashAuthError(QDashHTTPError):
    """Authentication/authorization error."""
    pass


def create_http_error(response) -> QDashHTTPError:
    """Create appropriate HTTP error from response object."""
    # Extract request info if available
    request_url = None
    if hasattr(response, 'request') and response.request:
        request_url = str(response.request.url)
    
    # Get response body safely
    response_body = None
    try:
        if hasattr(response, 'content'):
            response_body = response.content.decode('utf-8', errors='ignore')
        elif hasattr(response, 'text'):
            response_body = response.text
    except (UnicodeDecodeError, AttributeError):
        response_body = "<Unable to decode response body>"
    
    # Get headers
    headers = {}
    if hasattr(response, 'headers'):
        headers = dict(response.headers)
    
    # Create appropriate error type based on status code
    status_code = getattr(response, 'status_code', 0)
    
    if status_code == 401:
        error_class = QDashAuthError
        message = "Authentication failed - check username or credentials"
    elif status_code == 403:
        error_class = QDashAuthError  
        message = "Access forbidden - insufficient permissions"
    elif status_code == 404:
        message = "Resource not found"
        error_class = QDashHTTPError
    elif status_code == 422:
        message = "Validation error - check request parameters"
        error_class = QDashHTTPError
    elif status_code == 429:
        message = "Rate limit exceeded - too many requests"
        error_class = QDashHTTPError
    elif 500 <= status_code < 600:
        message = "Server error - please try again later"
        error_class = QDashHTTPError
    else:
        message = f"HTTP request failed with status {status_code}"
        error_class = QDashHTTPError
    
    return error_class(
        message=message,
        status_code=status_code,
        response_body=response_body,
        headers=headers,
        request_url=request_url
    )