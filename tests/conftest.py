"""
Shared pytest fixtures and mock helpers for the scrapling-knowledge-engine test suite.
All external I/O (HTTP requests, DDGS, Scrapling fetchers) is mocked at the module
boundary so tests run fully offline with no network access.
"""
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Generic HTTP response factory
# ---------------------------------------------------------------------------

def make_response(status_code: int = 200, json_data=None, text: str = "", headers: dict | None = None):
    """Build a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {"Content-Type": "application/json"}
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("no JSON")

    # raise_for_status: only raises on 4xx/5xx
    if status_code >= 400:
        from requests.exceptions import HTTPError
        resp.raise_for_status.side_effect = HTTPError(
            f"{status_code} Error", response=resp
        )
    else:
        resp.raise_for_status.return_value = None

    return resp


# ---------------------------------------------------------------------------
# GitHub API fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def gh_tree_response():
    """Minimal GitHub tree API response with one .py and one .md file."""
    return make_response(
        json_data={
            "tree": [
                {"type": "blob", "path": "README.md", "sha": "abc123"},
                {"type": "blob", "path": "app/server.py", "sha": "def456"},
                {"type": "blob", "path": "app/tools/__init__.py", "sha": "ghi789"},
                {"type": "tree", "path": "app/tools", "sha": "jkl000"},  # directory — should be ignored
            ]
        }
    )


@pytest.fixture
def gh_raw_content_response():
    """Minimal raw file response."""
    return make_response(text="print('hello world')")


@pytest.fixture
def gh_issues_response():
    """Minimal GitHub issues API response — one issue, one PR (PR should be skipped)."""
    return make_response(
        json_data=[
            {
                "number": 1,
                "title": "Bug: something broken",
                "state": "open",
                "user": {"login": "alice"},
                "labels": [{"name": "bug"}],
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
                "body": "Something is broken.",
                "comments": 0,
                "comments_url": "https://api.github.com/repos/owner/repo/issues/1/comments",
                "html_url": "https://github.com/owner/repo/issues/1",
            },
            {
                "number": 2,
                "title": "PR: add feature",
                "state": "open",
                "user": {"login": "bob"},
                "labels": [],
                "created_at": "2024-01-03T00:00:00Z",
                "updated_at": "2024-01-03T00:00:00Z",
                "body": "Adds a feature.",
                "comments": 0,
                "comments_url": "https://api.github.com/repos/owner/repo/issues/2/comments",
                "html_url": "https://github.com/owner/repo/pull/2",
                "pull_request": {"url": "https://api.github.com/repos/owner/repo/pulls/2"},
            },
        ]
    )


@pytest.fixture
def gh_issues_with_comments_response():
    """Issue that has 1 comment."""
    return make_response(
        json_data=[
            {
                "number": 3,
                "title": "Issue with comments",
                "state": "open",
                "user": {"login": "carol"},
                "labels": [],
                "created_at": "2024-02-01T00:00:00Z",
                "updated_at": "2024-02-01T00:00:00Z",
                "body": "Body text.",
                "comments": 1,
                "comments_url": "https://api.github.com/repos/owner/repo/issues/3/comments",
                "html_url": "https://github.com/owner/repo/issues/3",
            }
        ]
    )


@pytest.fixture
def gh_comments_response():
    return make_response(
        json_data=[
            {
                "user": {"login": "dave"},
                "body": "This is a comment.",
                "created_at": "2024-02-01T12:00:00Z",
            }
        ]
    )


@pytest.fixture
def gh_code_search_response():
    return make_response(
        json_data={
            "items": [
                {
                    "repository": {"full_name": "owner/repo"},
                    "path": "app/server.py",
                    "html_url": "https://github.com/owner/repo/blob/main/app/server.py",
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# OpenAPI fixtures
# ---------------------------------------------------------------------------

OPENAPI3_JSON = {
    "openapi": "3.0.0",
    "info": {"title": "Test API", "version": "1.0.0"},
    "servers": [{"url": "https://api.example.com"}],
    "paths": {
        "/users": {
            "get": {
                "operationId": "listUsers",
                "summary": "List users",
                "tags": ["users"],
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer"},
                        "description": "Max results",
                    }
                ],
                "responses": {"200": {"description": "OK"}},
            },
            "post": {
                "operationId": "createUser",
                "summary": "Create user",
                "tags": ["users"],
                "parameters": [],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "properties": {"name": {}, "email": {}}
                            }
                        }
                    },
                },
                "responses": {"201": {"description": "Created"}},
            },
        }
    },
}

SWAGGER2_JSON = {
    "swagger": "2.0",
    "info": {"title": "Swagger API", "version": "0.1"},
    "host": "swagger.example.com",
    "basePath": "/v1",
    "schemes": ["https"],
    "paths": {
        "/items": {
            "get": {
                "operationId": "listItems",
                "summary": "List items",
                "parameters": [],
                "responses": {"200": {"description": "OK"}},
            }
        }
    },
}

OPENAPI_YAML_TEXT = """
openapi: "3.0.0"
info:
  title: YAML API
  version: "2.0.0"
servers:
  - url: https://yaml.example.com
paths:
  /ping:
    get:
      operationId: ping
      summary: Ping endpoint
      parameters: []
      responses:
        "200":
          description: pong
"""


@pytest.fixture
def openapi3_response():
    import json
    return make_response(text=json.dumps(OPENAPI3_JSON))


@pytest.fixture
def swagger2_response():
    import json
    return make_response(text=json.dumps(SWAGGER2_JSON))


@pytest.fixture
def openapi_yaml_response():
    return make_response(
        text=OPENAPI_YAML_TEXT,
        headers={"Content-Type": "application/yaml"},
    )


# ---------------------------------------------------------------------------
# GraphQL fixtures
# ---------------------------------------------------------------------------

GQL_INTROSPECTION_RESPONSE = {
    "data": {
        "__schema": {
            "queryType": {"name": "Query"},
            "mutationType": {"name": "Mutation"},
            "subscriptionType": None,
            "types": [
                {
                    "kind": "OBJECT",
                    "name": "Query",
                    "description": "Root query",
                    "fields": [
                        {
                            "name": "user",
                            "description": "Get a user",
                            "args": [
                                {
                                    "name": "id",
                                    "description": "",
                                    "type": {
                                        "kind": "NON_NULL",
                                        "name": None,
                                        "ofType": {"kind": "SCALAR", "name": "ID", "ofType": None},
                                    },
                                }
                            ],
                            "type": {"kind": "OBJECT", "name": "User", "ofType": None},
                            "isDeprecated": False,
                            "deprecationReason": None,
                        }
                    ],
                    "inputFields": None,
                    "enumValues": None,
                    "possibleTypes": None,
                },
                {
                    "kind": "OBJECT",
                    "name": "Mutation",
                    "description": "Root mutation",
                    "fields": [
                        {
                            "name": "createUser",
                            "description": "Create a user",
                            "args": [],
                            "type": {"kind": "OBJECT", "name": "User", "ofType": None},
                            "isDeprecated": False,
                            "deprecationReason": None,
                        }
                    ],
                    "inputFields": None,
                    "enumValues": None,
                    "possibleTypes": None,
                },
                {
                    "kind": "OBJECT",
                    "name": "User",
                    "description": "A user object",
                    "fields": [
                        {
                            "name": "id",
                            "description": "",
                            "args": [],
                            "type": {"kind": "SCALAR", "name": "ID", "ofType": None},
                            "isDeprecated": False,
                            "deprecationReason": None,
                        },
                        {
                            "name": "name",
                            "description": "",
                            "args": [],
                            "type": {
                                "kind": "LIST",
                                "name": None,
                                "ofType": {"kind": "SCALAR", "name": "String", "ofType": None},
                            },
                            "isDeprecated": True,
                            "deprecationReason": "Use fullName",
                        },
                    ],
                    "inputFields": None,
                    "enumValues": None,
                    "possibleTypes": None,
                },
                {
                    "kind": "ENUM",
                    "name": "Role",
                    "description": "User roles",
                    "fields": None,
                    "inputFields": None,
                    "enumValues": [{"name": "ADMIN"}, {"name": "USER"}],
                    "possibleTypes": None,
                },
                # Built-in — must be filtered out
                {
                    "kind": "OBJECT",
                    "name": "__Schema",
                    "description": "introspection type",
                    "fields": [],
                    "inputFields": None,
                    "enumValues": None,
                    "possibleTypes": None,
                },
            ],
        }
    }
}


@pytest.fixture
def gql_response():
    return make_response(json_data=GQL_INTROSPECTION_RESPONSE)
