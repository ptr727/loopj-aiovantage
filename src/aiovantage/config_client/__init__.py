"""Client for the Vantage Application Communication Interface (ACI) service.

The ACI service is an XML-based RPC service that Design Center uses to communicate
with Vantage InFusion Controllers. There are a number of "interfaces" exposed, each
with one or more "methods".

This service allows you to query the "configuration" of a Vantage system, for
example fetching a list of all the objects, getting a backup of the Design Center
XML, etc.

The service is exposed on port 2010 (SSL) by default, and on port 2001 (non-SSL) if
this port has been opened by the firewall on the controller.

The service is discoverable via mDNS as `_aci._tcp.local` and/or
`_secure_aci._tcp.local`.
"""

import logging
from ssl import SSLContext
from types import TracebackType
from typing import Optional, Type, Union
from xml.etree import ElementTree

from typing_extensions import Self
from xsdata.formats.dataclass.parsers import XmlParser
from xsdata.formats.dataclass.parsers.config import ParserConfig
from xsdata.formats.dataclass.parsers.handlers import XmlEventHandler
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig

from aiovantage.config_client.methods import Call, Method, Return
from aiovantage.config_client.methods.login import Login
from aiovantage.connection import BaseConnection
from aiovantage.errors import LoginFailedError


class ConfigConnection(BaseConnection):
    """Connection to a Vantage ACI server."""

    default_port = 2001
    default_ssl_port = 2010
    default_conn_timeout = 5.0
    default_read_timeout = 30.0
    buffer_limit = 2**20

    async def request(self, interface: str, payload: str) -> str:
        """Send a request and return the response."""

        async with self._lock:
            # Send the request
            await self.write(f"<{interface}>{payload}</{interface}>")

            # Read the response
            return await self.readuntil_with_timeout(f"</{interface}>")


class ConfigClient:
    """Client for the Vantage Application Communication Interface (ACI) service.

    This client handles connecting to the ACI service, authenticating, and the
    serialization/deserialization of XML requests and responses.
    """

    def __init__(
        self,
        host: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        *,
        ssl: Union[SSLContext, bool] = True,
        port: Optional[int] = None,
        conn_timeout: float = 5,
        read_timeout: float = 30,
    ) -> None:
        """Initialize the client."""

        self._username = username
        self._password = password
        self._connection = ConfigConnection(
            host,
            port=port,
            ssl=ssl,
            conn_timeout=conn_timeout,
            read_timeout=read_timeout,
        )

        self._serializer = XmlSerializer(
            config=SerializerConfig(xml_declaration=False),
        )

        self._parser = XmlParser(
            config=ParserConfig(fail_on_unknown_properties=False),
            handler=XmlEventHandler,
        )

        self._logger = logging.getLogger(__name__)

    async def __aenter__(self) -> Self:
        """Return context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Exit context manager."""
        self.close()

        if exc_val:
            raise exc_val

    def close(self) -> None:
        """Close the connection to the ACI service."""
        self._connection.close()

    async def request(
        self,
        method_cls: Type[Method[Call, Return]],
        params: Optional[Call] = None,
    ) -> Return:
        """Marshall a request, send it to the ACI service, and return a parsed object.

        Args:
            method_cls: The method class to use
            params: The parameters instance to pass to the method

        Returns:
            The parsed response object
        """

        # Open the connection if it's closed
        await self._ensure_connected()

        # Build the method object
        method = method_cls()
        method.call = params
        method_name = f"{method_cls.interface}.{method_cls.__name__}"

        # Render the method object to XML with xsdata
        request = self._serializer.render(method)
        self._logger.debug(request)
        response = await self._connection.request(method.interface, request)
        self._logger.debug(response)

        # Parse the XML doc and extract the method element
        tree = ElementTree.fromstring(response)
        method_el = tree.find(f"{method_cls.__name__}")
        if method_el is None:
            raise ValueError(f"<{method_cls.__name__}> element missing from response")

        # Validate there is a non-empty return value
        return_el = method_el.find("return")
        if return_el is None:
            raise ValueError(f"{method_name} response did not contain a return value")

        # Parse the method element with xsdata
        method = self._parser.parse(method_el, method_cls)
        if method.return_value is None:
            raise ValueError(f"{method_name} response did not contain a return value")

        return method.return_value

    async def _ensure_connected(self) -> None:
        # Ensure the connection is open.

        if self._connection.closed:
            await self._connection.open()

            # Log in if we have credentials
            if self._username is not None and self._password is not None:
                success = await self.request(
                    Login, Login.Params(self._username, self._password)
                )

                if not success:
                    raise LoginFailedError("Login failed, bad username or password")
