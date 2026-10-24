"""
Tests for app/tools/api.py

Coverage targets:
  - fetch_openapi_spec: JSON (OpenAPI 3.x), JSON (Swagger 2.x), YAML, invalid JSON,
                        invalid YAML, non-dict parsed result, HTTP error,
                        missing PyYAML, request body extraction, no servers block
  - _unwrap_type: NON_NULL, LIST, nested, plain scalar, non-dict input
  - fetch_graphql_schema: success (queries/mutations/types/enums), introspection errors,
                          no __schema, JSON decode error, HTTP error, custom headers
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from requests.exceptions import ConnectionError as ReqConnectionError

from app.tools.api import fetch_openapi_spec, fetch_graphql_schema, _unwrap_type
from tests.conftest import (
    make_response,
    OPENAPI3_JSON,
    SWAGGER2_JSON,
    OPENAPI_YAML_TEXT,
    GQL_INTROSPECTION_RESPONSE,
)


# ===========================================================================
# _unwrap_type
# ===========================================================================

class TestUnwrapType:
    def test_plain_scalar(self):
        assert _unwrap_type({"kind": "SCALAR", "name": "String", "ofType": None}) == "String"

    def test_non_null(self):
        t = {"kind": "NON_NULL", "name": None, "ofType": {"kind": "SCALAR", "name": "ID", "ofType": None}}
        assert _unwrap_type(t) == "ID!"

    def test_list(self):
        t = {"kind": "LIST", "name": None, "ofType": {"kind": "SCALAR", "name": "String", "ofType": None}}
        assert _unwrap_type(t) == "[String]"

    def test_non_null_list(self):
        inner = {"kind": "LIST", "name": None, "ofType": {"kind": "SCALAR", "name": "Int", "ofType": None}}
        t = {"kind": "NON_NULL", "name": None, "ofType": inner}
        assert _unwrap_type(t) == "[Int]!"

    def test_list_of_non_null(self):
        scalar = {"kind": "SCALAR", "name": "Float", "ofType": None}
        nn = {"kind": "NON_NULL", "name": None, "ofType": scalar}
        t = {"kind": "LIST", "name": None, "ofType": nn}
        assert _unwrap_type(t) == "[Float!]"

    def test_non_dict_returns_unknown(self):
        assert _unwrap_type(None) == "Unknown"
        assert _unwrap_type("String") == "Unknown"

    def test_no_name_returns_unknown(self):
        assert _unwrap_type({"kind": "SCALAR", "name": None, "ofType": None}) == "Unknown"


# ===========================================================================
# fetch_openapi_spec
# ===========================================================================

class TestFetchOpenApiSpec:
    @patch("app.tools.api.requests.get")
    def test_openapi3_json_success(self, mock_get, openapi3_response):
        mock_get.return_value = openapi3_response
        result = fetch_openapi_spec("https://example.com/openapi.json")
        assert "error" not in result
        assert result["title"] == "Test API"
        assert result["version"] == "1.0.0"
        assert result["openapi_version"] == "3.0.0"
        assert result["base_url"] == "https://api.example.com"
        assert result["endpoint_count"] == 2

    @patch("app.tools.api.requests.get")
    def test_openapi3_endpoints_shape(self, mock_get, openapi3_response):
        mock_get.return_value = openapi3_response
        result = fetch_openapi_spec("https://example.com/openapi.json")
        get_ep = next(e for e in result["endpoints"] if e["method"] == "GET")
        assert get_ep["path"] == "/users"
        assert get_ep["operation_id"] == "listUsers"
        assert get_ep["summary"] == "List users"
        assert any(p["name"] == "limit" for p in get_ep["parameters"])
        assert get_ep["request_body"] is None

    @patch("app.tools.api.requests.get")
    def test_openapi3_request_body_extracted(self, mock_get, openapi3_response):
        mock_get.return_value = openapi3_response
        result = fetch_openapi_spec("https://example.com/openapi.json")
        post_ep = next(e for e in result["endpoints"] if e["method"] == "POST")
        assert post_ep["request_body"] is not None
        assert post_ep["request_body"]["media_type"] == "application/json"
        assert "name" in post_ep["request_body"]["properties"]

    @patch("app.tools.api.requests.get")
    def test_swagger2_json_success(self, mock_get, swagger2_response):
        mock_get.return_value = swagger2_response
        result = fetch_openapi_spec("https://example.com/swagger.json")
        assert result["title"] == "Swagger API"
        assert result["openapi_version"] == "2.0"
        assert result["base_url"] == "https://swagger.example.com/v1"
        assert result["endpoint_count"] == 1

    @patch("app.tools.api.requests.get")
    def test_yaml_spec_success(self, mock_get, openapi_yaml_response):
        mock_get.return_value = openapi_yaml_response
        result = fetch_openapi_spec("https://example.com/openapi.yaml")
        assert "error" not in result
        assert result["title"] == "YAML API"
        assert result["version"] == "2.0.0"
        assert result["endpoint_count"] == 1

    @patch("app.tools.api.requests.get")
    def test_http_error_returns_error(self, mock_get):
        mock_get.side_effect = ReqConnectionError("refused")
        result = fetch_openapi_spec("https://example.com/openapi.json")
        assert "error" in result
        assert "Failed to fetch" in result["error"]

    @patch("app.tools.api.requests.get")
    def test_invalid_json_returns_error(self, mock_get):
        mock_get.return_value = make_response(text="not json at all }{")
        result = fetch_openapi_spec("https://example.com/spec.json")
        assert "error" in result
        assert "parse JSON" in result["error"]

    @patch("app.tools.api.requests.get")
    def test_invalid_yaml_returns_error(self, mock_get):
        mock_get.return_value = make_response(
            text=": : invalid: yaml: !!!\n  bad indent",
            headers={"Content-Type": "application/yaml"},
        )
        result = fetch_openapi_spec("https://example.com/spec.yaml")
        assert "error" in result

    @patch("app.tools.api.requests.get")
    def test_non_dict_parsed_result_returns_error(self, mock_get):
        mock_get.return_value = make_response(text=json.dumps([1, 2, 3]))
        result = fetch_openapi_spec("https://example.com/spec.json")
        assert "error" in result
        assert "not a valid" in result["error"]

    @patch("app.tools.api.requests.get")
    def test_spec_with_no_servers_key(self, mock_get):
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "No Server API", "version": "1.0"},
            "paths": {},
        }
        mock_get.return_value = make_response(text=json.dumps(spec))
        result = fetch_openapi_spec("https://example.com/spec.json")
        assert result["base_url"] == ""
        assert result["endpoint_count"] == 0

    @patch("app.tools.api.YAML_AVAILABLE", False)
    @patch("app.tools.api.requests.get")
    def test_yaml_without_pyyaml_installed(self, mock_get):
        mock_get.return_value = make_response(
            text="openapi: 3.0.0",
            headers={"Content-Type": "application/yaml"},
        )
        result = fetch_openapi_spec("https://example.com/spec.yaml")
        assert "error" in result
        assert "PyYAML" in result["error"]

    @patch("app.tools.api.requests.get")
    def test_path_level_parameters_merged(self, mock_get):
        """Parameters defined at path level should be included per operation."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/items/{id}": {
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}, "description": "Item ID"}
                    ],
                    "get": {
                        "summary": "Get item",
                        "parameters": [],
                        "responses": {"200": {"description": "OK"}},
                    },
                }
            },
        }
        mock_get.return_value = make_response(text=json.dumps(spec))
        result = fetch_openapi_spec("https://example.com/spec.json")
        ep = result["endpoints"][0]
        assert any(p["name"] == "id" for p in ep["parameters"])


# ===========================================================================
# fetch_graphql_schema
# ===========================================================================

class TestFetchGraphqlSchema:
    @patch("app.tools.api.requests.post")
    def test_success_returns_schema(self, mock_post, gql_response):
        mock_post.return_value = gql_response
        result = fetch_graphql_schema("https://api.example.com/graphql")
        assert "error" not in result
        assert result["query_type"] == "Query"
        assert result["mutation_type"] == "Mutation"
        assert result["subscription_type"] is None

    @patch("app.tools.api.requests.post")
    def test_queries_extracted(self, mock_post, gql_response):
        mock_post.return_value = gql_response
        result = fetch_graphql_schema("https://api.example.com/graphql")
        assert result["query_count"] == 1
        query_field = result["queries"][0]
        assert query_field["name"] == "user"
        assert "id: ID!" in query_field["args"]

    @patch("app.tools.api.requests.post")
    def test_mutations_extracted(self, mock_post, gql_response):
        mock_post.return_value = gql_response
        result = fetch_graphql_schema("https://api.example.com/graphql")
        assert result["mutation_count"] == 1
        assert result["mutations"][0]["name"] == "createUser"

    @patch("app.tools.api.requests.post")
    def test_user_types_extracted(self, mock_post, gql_response):
        mock_post.return_value = gql_response
        result = fetch_graphql_schema("https://api.example.com/graphql")
        type_names = [t["name"] for t in result["types"]]
        assert "User" in type_names
        assert "Role" in type_names

    @patch("app.tools.api.requests.post")
    def test_builtin_types_filtered_out(self, mock_post, gql_response):
        mock_post.return_value = gql_response
        result = fetch_graphql_schema("https://api.example.com/graphql")
        type_names = [t["name"] for t in result["types"]]
        assert "__Schema" not in type_names

    @patch("app.tools.api.requests.post")
    def test_enum_values_extracted(self, mock_post, gql_response):
        mock_post.return_value = gql_response
        result = fetch_graphql_schema("https://api.example.com/graphql")
        role_type = next(t for t in result["types"] if t["name"] == "Role")
        assert "ADMIN" in role_type["enum_values"]
        assert "USER" in role_type["enum_values"]

    @patch("app.tools.api.requests.post")
    def test_deprecated_field_flagged(self, mock_post, gql_response):
        mock_post.return_value = gql_response
        result = fetch_graphql_schema("https://api.example.com/graphql")
        user_type = next(t for t in result["types"] if t["name"] == "User")
        name_field = next(f for f in user_type["fields"] if f["name"] == "name")
        assert name_field["deprecated"] is True

    @patch("app.tools.api.requests.post")
    def test_list_type_unwrapped_in_field(self, mock_post, gql_response):
        mock_post.return_value = gql_response
        result = fetch_graphql_schema("https://api.example.com/graphql")
        user_type = next(t for t in result["types"] if t["name"] == "User")
        name_field = next(f for f in user_type["fields"] if f["name"] == "name")
        assert name_field["type"] == "[String]"

    @patch("app.tools.api.requests.post")
    def test_graphql_errors_in_response(self, mock_post):
        mock_post.return_value = make_response(
            json_data={"errors": [{"message": "introspection disabled"}]}
        )
        result = fetch_graphql_schema("https://api.example.com/graphql")
        assert "error" in result
        assert "GraphQL returned errors" in result["error"]
        assert "graphql_errors" in result

    @patch("app.tools.api.requests.post")
    def test_no_schema_in_data(self, mock_post):
        mock_post.return_value = make_response(json_data={"data": {}})
        result = fetch_graphql_schema("https://api.example.com/graphql")
        assert "error" in result
        assert "No __schema" in result["error"]

    @patch("app.tools.api.requests.post")
    def test_json_decode_error(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        resp.json.side_effect = ValueError("not JSON")
        mock_post.return_value = resp
        result = fetch_graphql_schema("https://api.example.com/graphql")
        assert "error" in result
        assert "parse GraphQL response" in result["error"]

    @patch("app.tools.api.requests.post")
    def test_http_error_returns_error(self, mock_post):
        mock_post.side_effect = ReqConnectionError("refused")
        result = fetch_graphql_schema("https://api.example.com/graphql")
        assert "error" in result
        assert "introspection request failed" in result["error"]

    @patch("app.tools.api.requests.post")
    def test_custom_headers_forwarded(self, mock_post, gql_response):
        mock_post.return_value = gql_response
        fetch_graphql_schema("https://api.example.com/graphql", headers={"Authorization": "Bearer tok"})
        call_headers = mock_post.call_args[1]["headers"]
        assert call_headers["Authorization"] == "Bearer tok"
        assert call_headers["Content-Type"] == "application/json"

    @patch("app.tools.api.requests.post")
    def test_no_subscription_type(self, mock_post, gql_response):
        mock_post.return_value = gql_response
        result = fetch_graphql_schema("https://api.example.com/graphql")
        assert result["subscription_type"] is None
        assert result["subscriptions"] == []
