import asyncio
import http
import json
import pathlib
from typing import Any, Callable, Dict, Tuple, Union

import aiopenapi3
import httpx as httpx
from aiopenapi3 import FileSystemLoader, OpenAPI
from openapi_schema_validator import OAS30Validator, validate
from test_engine_core.interfaces.imodel import IModel
from test_engine_core.plugins.enums.model_plugin_type import ModelPluginType
from test_engine_core.plugins.enums.plugin_type import PluginType
from test_engine_core.plugins.metadata.plugin_metadata import PluginMetadata


# NOTE: Do not change the class name, else the plugin cannot be read by the system
class Plugin(IModel):
    """
    The Plugin(OpenAPIConnector) class specifies methods on
    handling methods in performing identifying, validating, predicting, scoring.
    """

    # Some information on plugin
    _name: str = "OpenAPIConnector"
    _description: str = (
        "OpenAPIConnector supports performing api calls to external model servers"
    )
    _version: str = "0.9.0"
    _metadata: PluginMetadata = PluginMetadata(_name, _description, _version)
    _plugin_type: PluginType = PluginType.MODEL
    _model_plugin_type: ModelPluginType = ModelPluginType.API
    _api_instance: Any = None
    _api_instance_schema: Any = None
    _api_validator: Any = OAS30Validator
    _api_schema: Dict = None
    _api_config: Dict = None
    # OpenAPI custom transport variables
    _api_verify: bool = False
    _api_rate_limit_timeout: float = 5.0
    _api_cert: Any = None
    _api_retries: int = 3
    # OpenAPI request error
    _lock = asyncio.Lock()
    _response_error_message: str = ""

    @staticmethod
    def get_metadata() -> PluginMetadata:
        """
        A method to return the metadata for this plugin

        Returns:
            PluginMetadata: Metadata of this plugin
        """
        return Plugin._metadata

    @staticmethod
    def get_plugin_type() -> PluginType:
        """
        A method to return the type for this plugin

        Returns:
             PluginType: Type of this plugin
        """
        return Plugin._plugin_type

    @staticmethod
    def get_model_plugin_type() -> ModelPluginType:
        """
        A method to return ModelPluginType

        Returns:
            ModelPluginType: Model Plugin Type
        """
        return Plugin._model_plugin_type

    @staticmethod
    def custom_session_factory(*args, **kwargs) -> httpx.AsyncClient:
        """
        A session factory that generates async client with custom transport module

        Returns:
            httpx.AsyncClient: Returns a httpx AsyncClient
        """
        kwargs["transport"] = OpenAPICustomTransport(
            verify=Plugin._api_verify,
            cert=Plugin._api_cert,
            retries=Plugin._api_retries,
            rate_limit_timeout=Plugin._api_rate_limit_timeout,
            response_error_callback=Plugin._notify_response_error,
        )
        return httpx.AsyncClient(*args, **kwargs)

    def __init__(self, **kwargs) -> None:
        # Configuration
        self._is_setup_completed = False
        self._api_instance = None
        api_schema = kwargs.get("api_schema", None)
        api_config = kwargs.get("api_config", None)

        if api_schema and api_config:
            self._api_schema = api_schema
            self._api_config = api_config
        else:
            self._api_schema: Dict = dict()
            self._api_config: Dict = dict()

    def cleanup(self) -> None:
        """
        A method to clean-up objects
        """
        pass

    def setup(self) -> Tuple[bool, str]:
        """
        A method to perform setup

        Returns:
            Tuple[bool, str]: Returns bool to indicate success, str will indicate the
            error message if failed.
        """
        try:
            # Perform OpenAPI3 schema validation
            # An exception will be thrown if validation has errors
            is_success, error_message = self._perform_validation()
            if not is_success:
                raise RuntimeError(error_message)

            # Search for the first api and http method.
            # Set the prediction operationId
            path_to_be_updated = self._api_schema["paths"]
            if len(path_to_be_updated) > 0:
                first_api = list(path_to_be_updated.items())[0]
                first_api_value = first_api[1]
                if len(first_api_value) > 0:
                    first_api_http = list(first_api_value.items())[0]
                    first_api_http_value = first_api_http[1]
                    first_api_http_value.update({"operationId": "predict_api"})

            # Update session variables if necessary
            # Plugin._api_verify = False
            # Plugin._api_rate_limit_timeout = 2.0
            # Plugin._api_retries = 3
            # Plugin._api_cert = None

            # Create the api instance based on the provided api schema
            self._api_instance = OpenAPI.loads(
                url="",
                data=json.dumps(self._api_schema),
                session_factory=Plugin.custom_session_factory,
                loader=FileSystemLoader(pathlib.Path("")),
                use_operation_tags=True,
            )

            # Setup API Authentication
            self._setup_api_authentication()

            # Setup completed
            self._is_setup_completed = True
            return True, ""

        except Exception as exception:
            return False, str(exception)

    def get_model(self) -> Any:
        """
        A method to return the model

        Returns:
            Any: Model
        """
        return None

    def get_model_algorithm(self) -> str:
        """
        A method to retrieve the connector name

        Returns:
            str: connector name
        """
        return self._name

    def is_supported(self) -> bool:
        """
        A method to check whether the model is being identified correctly
        and is supported

        Returns:
            bool: True if is an instance of model and is supported
        """
        is_success, _ = self._perform_validation()
        return is_success

    def predict(self, data: Any, *args) -> Any:
        """
        A method to perform prediction using the model

        Args:
            data (Any): data to be predicted by the model

        Returns:
            Any: predicted result
        """
        # Call the function to make multiple requests
        try:
            responses = asyncio.run(self.make_requests())
            print(responses.text)
        except aiopenapi3.RequestError:
            raise RuntimeError(Plugin._response_error_message)

    def predict_proba(self, data: Any, *args) -> Any:
        """
        A method to perform prediction probability using the model

        Args:
            data (Any): data to be predicted by the model

        Returns:
            Any: predicted result
        """
        pass

    def score(self, data: Any, y_true: Any) -> Any:
        """
        A method to perform scoring using the model

        Args:
            data (Any): data to be scored with y_true
            y_true (Any): ground truth

        Returns:
            Any: score result
        """
        raise RuntimeError("OpenAPIConnector does not support score method")

    @staticmethod
    async def _get_response_error() -> str:
        """
        An async method to return the error message detected during response

        Returns:
            str: Contains the error message
        """
        async with Plugin._lock:
            return Plugin._response_error_message

    @staticmethod
    async def _notify_response_error(error_message: str):
        """
        An async method to set the error message detected during response

        Args:
            error_message (str): Contains the error message
        """
        async with Plugin._lock:
            Plugin._response_error_message = error_message

    async def get_schema_content(self) -> Any:
        """
        An async method that returns the schema content for the api instance

        Raises:
            NotImplementedError: Exception if the requestBody content is not supported such as
            "application/json", "multipart/form-data", "application/x-www-form-urlencoded"

        Returns:
            Any: API schema content
        """
        if (
            "application/json"
            in self._api_instance._.predict_api.operation.requestBody.content
        ):
            return self._api_instance._.predict_api.operation.requestBody.content[
                "application/json"
            ].schema_
        elif (
            ct := "multipart/form-data"
        ) in self._api_instance._.predict_api.operation.requestBody.content:
            return self._api_instance._.predict_api.operation.requestBody.content[
                ct
            ].schema_
        elif (
            ct := "application/x-www-form-urlencoded"
        ) in self._api_instance._.predict_api.operation.requestBody.content:
            return self._api_instance._.predict_api.operation.requestBody.content[
                ct
            ].schema_
        else:
            raise NotImplementedError(
                self._api_instance._.predict_api.operation.requestBody.content
            )

    async def make_requests(self) -> Any:
        """
        An async method that performs openapi3 requests through the library

        Raises:
            RuntimeError: Exception if method is not supported such as "post" and "get"

        Returns:
            Any: Response result
        """
        if self._api_instance._.predict_api.method.lower() == "post":
            # Get API Instance schema
            self._api_instance_schema = await self.get_schema_content()

            # Populate headers
            headers = dict()
            for parameter in self._api_instance._.predict_api.parameters:
                if str(parameter.in_.name).lower() == "header" and parameter.required:
                    if len(parameter.schema_.enum) > 0:
                        headers.update({parameter.name: parameter.schema_.enum[0]})

            # Populate body with payload values
            payload = {
                "age": 1,
                "gender": 2,
                "race": 3,
                "income": 4,
                "employment": 5,
                "employment_length": 6,
                "total_donated": 7,
                "num_donation": 8,
            }
            body = self._api_instance_schema.get_type().construct(**payload)

            # Perform api request
            headers, data, result = await self._api_instance._.predict_api.request(
                parameters=headers, data=body
            )

        elif self._api_instance._.predict_api.method.lower() == "get":
            # Populate headers
            headers = {
                "age": 1,
                "gender": 2,
                "race": 3,
                "income": 4,
                "employment": 5,
                "employment_length": 6,
                "total_donated": 7,
                "num_donation": 8,
            }

            # Populate body with payload values
            body = None

            # Perform api request
            headers, data, result = await self._api_instance._.predict_api.request(
                parameters=headers, data=body
            )

        else:
            raise RuntimeError("Unexpected api method")

        return result

    def _setup_api_authentication(self) -> None:
        """
        A method to perform setup for api authentication
        """
        # Identify the securitySchemes key
        api_key_list = list(self._api_instance.components.securitySchemes.keys())
        for api_key in api_key_list:
            # Get the api security type and scheme
            scheme_type = self._api_instance.components.securitySchemes[
                api_key
            ].type.lower()
            if scheme_type == "http":
                http_scheme = self._api_instance.components.securitySchemes[
                    api_key
                ].scheme_.lower()
                if http_scheme == "bearer":
                    api_token = self._api_config.get("authentication", {}).get(
                        "token", ""
                    )
                    self._api_instance.authenticate(**{api_key: str(api_token)})
                elif http_scheme == "basic":
                    api_username = self._api_config.get("authentication", {}).get(
                        "username", ""
                    )
                    api_password = self._api_config.get("authentication", {}).get(
                        "password", ""
                    )
                    self._api_instance.authenticate(
                        **{api_key: (api_username, api_password)}
                    )
            else:
                pass

    def _perform_validation(self) -> Tuple[bool, str]:
        """
        A method to perform validation on openapi schema and configuration

        Returns:
            Tuple[bool, str]: Returns bool to indicate success, str will indicate the
            error message if failed.
        """
        try:
            validate(self._api_config, self._api_schema, cls=self._api_validator)
            return True, ""
        except Exception as error:
            return False, str(error)


class OpenAPICustomTransport(httpx.AsyncHTTPTransport):
    """
    A custom transport module that allows error code retries and backoff timing
    """

    _ssl_verify: bool = True
    _ssl_cert: Any = None
    _api_retries: int = 3
    # (1s, 2s, 4s)  Formula: {backoff factor} * (2 ** ({number of total retries} - 1))
    _api_backoff_factor: float = 2.0
    _api_rate_limit_timeout: float = 5.0  # seconds
    _api_status_code: list = [429, 500, 502, 503, 504]

    def __init__(
        self,
        verify: bool,
        cert: Any,
        retries: int,
        rate_limit_timeout: float,
        response_error_callback: Callable,
    ):
        # Save the variables
        self._ssl_verify = verify
        self._ssl_cert = cert
        self._api_retries = retries
        self._api_rate_limit_timeout = rate_limit_timeout
        self._response_error_callback = response_error_callback

        # Initialize super class
        super().__init__(
            verify=self._ssl_verify, cert=self._ssl_cert, retries=self._api_retries
        )

    async def handle_attempt_retries(
        self, attempt: int, status_code: Union[None, int]
    ) -> None:
        """
        An async method to handle the number of retries attempts and handle the backoff strategy
        when having issues with connecting to server. When faced with 429 status code,
        it will use the rate limit timeout instead of backoff strategy factor timeout.

        Args:
            attempt (int): current number of retry attempt
            status_code (Union[None, int]): response status code
        """
        if attempt == self._api_retries:
            return

        # Have not reached the number of retries.
        # Proceed to check backoff time and perform sleep
        if status_code and status_code == 429:
            # if the status code is 429 (too many requests)
            backoff_timing = self._api_rate_limit_timeout
        else:
            backoff_timing = int(self._api_backoff_factor * (2 ** (attempt - 1)))
        await asyncio.sleep(backoff_timing)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """
        An async method to handle incoming async requests before passing to query the server.
        This custom handling adds additional support for retry attempts for not able to connect or
        response codes that appear in the error code list.

        Args:
            request (httpx.Request): Incoming httpx async request for handling

        Raises:
            RuntimeError: Exception if the maximum retries is exceeded.
            The error message will be stored in the response error callback for display.

        Returns:
            httpx.Response: The response that is not within the error code list
        """
        # Send the async request to the server
        error_message = ""
        for attempt in range(self._api_retries + 1):
            try:
                response = await super().handle_async_request(request)
            except (
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.NetworkError,
            ) as exception:
                error_message = f"{str(exception)}"
                await self.handle_attempt_retries(attempt, None)
            else:
                if response.status_code not in self._api_status_code:
                    # Assume that the response is okay, not in the list of error status codes
                    return response
                else:
                    # The response status code in list of retries status code.
                    # Proceed to attempt retries
                    error_message = (
                        f"Response status code: {response.status_code} "
                        f"({http.HTTPStatus(response.status_code).name})"
                    )
                    await self.handle_attempt_retries(attempt, response.status_code)
            finally:
                # Exceeded the number of attempts
                if attempt == self._api_retries:
                    await self._response_error_callback(
                        f"Maximum retries exceeded ({self._api_retries}) {error_message}"
                    )
                    raise RuntimeError(
                        f"Maximum retries exceeded ({self._api_retries}) {error_message}"
                    )
