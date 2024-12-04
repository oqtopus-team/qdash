from pydantic import BaseModel


class SuccessResponse(BaseModel):
    message: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message": "Successfuly {message}",
                }
            ]
        }
    }
