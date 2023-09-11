"""Base class for command client interfaces."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Dict, Optional, Sequence, Type, TypeVar, Union, cast

from aiovantage.command_client import CommandClient
from aiovantage.command_client.utils import encode_params, tokenize_response

T = TypeVar("T")


@dataclass
class InterfaceResponse:
    """Wrapper for object interface invoke/status responses."""

    vid: int
    result: str
    method: str
    args: Sequence[str]


class Interface:
    """Base class for command client object interfaces."""

    response_parsers: Dict[str, Callable[[InterfaceResponse], Any]] = {}

    def __init__(self, client: CommandClient) -> None:
        """Initialize an object interface for standalone use.

        Args:
            client: The command client to use.
        """
        self._command_client = client

    @property
    def command_client(self) -> CommandClient:
        """Return the command client."""
        return self._command_client

    async def invoke(
        self,
        vid: int,
        method: str,
        *params: Union[str, int, float, Decimal],
        as_type: Optional[Type[T]] = None,
    ) -> T:
        """Invoke a method on an object, and wait for a response.

        Args:
            vid: The VID of the object to invoke the command on.
            method: The method to invoke.
            params: The parameters to send with the method.
            as_type: The type to parse the response as.

        Returns:
            An InterfaceResponse instance.
        """
        request = f"INVOKE {vid} {method}"
        if params:
            request += f" {encode_params(*params)}"

        # Send the request
        raw_response = await self.command_client.raw_request(request)

        # Parse the response
        _, vid_str, result, _, *args = tokenize_response(raw_response[-1])
        response = InterfaceResponse(int(vid_str), result, method, args)

        # Instances can inherit from multiple interfaces, so let's find the response
        # parser for the method we just invoked.
        for klass in type(self).__bases__:
            if issubclass(klass, Interface) and klass.response_parsers.get(method):
                return klass.parse_response(response, as_type)

        raise NotImplementedError(f"No response parser found for method {method}.")

    @classmethod
    def parse_response(
        cls, response: InterfaceResponse, as_type: Optional[Type[T]] = None
    ) -> T:
        """Parse a response from an object interface.

        Args:
            response: The response to parse.
            as_type: The type to parse the response as.

        Returns:
            The parsed response.
        """
        return cast(T, cls.response_parsers[response.method](response))
