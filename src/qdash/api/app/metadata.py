"""FastAPI metadata configuration for QDash API."""

from typing import Any

API_METADATA: dict[str, Any] = {
    "title": "QDash API",
    "description": "API for QDash",
    "summary": "QDash API",
    "version": "0.0.1",
    "contact": {
        "name": "QDash",
        "email": "oqtopus-team@googlegroups.com",
    },
    "license_info": {
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
}

OPENAPI_EXTRA: dict[str, Any] = {
    "components": {
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "description": "Bearer token authentication. Use the access_token from login response.",
            }
        }
    },
    "security": [{"BearerAuth": []}],
}
