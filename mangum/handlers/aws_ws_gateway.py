from typing import Any, Dict, Tuple
import base64
import logging
import json

from ..types import Response, WsRequest
from .abstract_handler import AbstractHandler

logger = logging.getLogger("mangum")
logger.setLevel(logging.INFO)


def get_server_and_headers(event: Dict[str, Any]) -> Tuple:  # pragma: no cover
    if event.get("multiValueHeaders"):
        headers = {
            k.lower(): ", ".join(v) if isinstance(v, list) else ""
            for k, v in event.get("multiValueHeaders", {}).items()
        }
    elif event.get("headers"):
        headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    else:
        headers = {}

    # Subprotocols are not supported, so drop Sec-WebSocket-Protocol to be safe
    headers.pop("sec-websocket-protocol", None)

    server_name = headers.get("host", "mangum")
    if ":" not in server_name:
        server_port = headers.get("x-forwarded-port", 80)
    else:
        server_name, server_port = server_name.split(":")
    server = (server_name, int(server_port))

    return server, headers


class AwsWsGateway(AbstractHandler):
    """
    Handles AWS API Gateway Websocket events, transforming
    them into ASGI Scope and handling responses

    See: https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html#api-gateway-simple-proxy-for-lambda-input-format  # noqa: E501
    """

    TYPE = "AWS_WS_GATEWAY"

    @property
    def request(self) -> WsRequest:
        request_context = self.trigger_event["requestContext"]
        logger.info(f"Mangum received event: {self.trigger_event}")
        server, headers = get_server_and_headers(self.trigger_event)
        path = headers.get("path", "/")
        source_ip = request_context.get("identity", {}).get("sourceIp")
        client = (source_ip, 0)
        headers_list = [[k.encode(), v.encode()] for k, v in headers.items()]

        logger.info(f"Mangum got path: {path}")
        return WsRequest(
            headers=headers_list,
            path=path,
            scheme=headers.get("x-forwarded-proto", "wss"),
            query_string=b"",
            server=server,
            client=client,
            trigger_event=self.trigger_event,
            trigger_context=self.trigger_context,
            event_type=self.TYPE,
        )

    @property
    def body(self) -> bytes:
        body = self.trigger_event.get("body", b"") or b""

        if self.trigger_event.get("isBase64Encoded", False):
            return base64.b64decode(body)
        if not isinstance(body, bytes):
            body = body.encode()

        return body

    def transform_response(self, response: Response) -> Dict[str, Any]:
        return {"statusCode": response.status}
