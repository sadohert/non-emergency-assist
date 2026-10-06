"""Webhook tool for the Non-Emergency Assist agent: takes a callback request and posts it to Mattermost."""

import hmac
import os
import re
import secrets

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

load_dotenv()

app = FastAPI(title="Non-Emergency Assist tools")


MARKDOWN_CHARS = re.compile(r"([\\`*_~\[\]()!|#<>])")


class CallbackRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    topic: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=500)
    first_name: str = Field(min_length=1, max_length=40)
    callback_number: str = Field(pattern=r"^[0-9+()\-. ]{7,20}$")

    @field_validator("callback_number")
    @classmethod
    def _has_a_real_number(cls, value: str) -> str:
        digits = sum(ch.isdigit() for ch in value)
        if not 7 <= digits <= 15:
            raise ValueError("callback_number must contain between 7 and 15 digits")
        return value


def _clean(text: str) -> str:
    """Flatten to one line, show Markdown literally, and stop @mentions notifying the channel."""
    one_line = " ".join(text.split())
    escaped = MARKDOWN_CHARS.sub(r"\\\1", one_line)
    return escaped.replace("@", "@​")


def _authorized(presented: str | None) -> bool:
    expected = os.environ.get("TOOL_SHARED_SECRET", "")
    if not expected or not presented:
        return False
    return hmac.compare_digest(presented, expected)


@app.post("/tools/request_callback")
def request_callback(req: CallbackRequest, x_tool_secret: str | None = Header(default=None)):
    if not _authorized(x_tool_secret):
        raise HTTPException(status_code=401, detail="unauthorized")

    reference = secrets.token_hex(3).upper()
    text = "\n".join(
        [
            f"#### Callback request `{reference}`",
            f"**Topic:** {_clean(req.topic)}",
            f"**Summary:** {_clean(req.summary)}",
            f"**Caller:** {_clean(req.first_name)}",
            f"**Number:** {_clean(req.callback_number)}",
            "_Logged by Non-Emergency Assist (unofficial demo)_",
        ]
    )

    try:
        resp = httpx.post(os.environ["MATTERMOST_WEBHOOK_URL"], json={"text": text}, timeout=5)
    except (httpx.HTTPError, KeyError) as exc:
        raise HTTPException(status_code=502, detail="could not reach staff channel") from exc
    if not resp.is_success:
        raise HTTPException(status_code=502, detail="staff channel rejected the request")

    return {"status": "queued", "reference": reference}
