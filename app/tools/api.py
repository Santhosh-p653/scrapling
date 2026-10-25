import json
import requests

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


# ---------------------------------------------------------------------------
# Tool: fetch_openapi_spec
# ---------------------------------------------------------------------------

def fetch_openapi_spec(url: str) -> dict:
    """
    Fetches and parses an OpenAPI 3.x or Swagger 2.x specification from a URL
    in JSON or YAML format.

    Returns a summarized tool map containing:
        title, version, openapi_version, base_url, endpoint_count, endpoints
    """
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"error": f"Failed to fetch OpenAPI spec: {str(e)}"}

    content_type = resp.headers.get("Content-Type", "")
    raw = resp.text

    # Parse JSON or YAML.
    spec = None

    if "json" in content_type.lower() or url.lower().split("?")[0].endswith(".json"):
        try:
            spec = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as e:
            return {"error": f"Failed to parse JSON spec: {str(e)}"}
    else:
        if not YAML_AVAILABLE:
            return {
                "error": (
                    "PyYAML is not installed. "
                    "Install with: pip install 'PyYAML>=6.0'"
                )
            }

        try:
            spec = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            return {"error": f"Failed to parse YAML spec: {str(e)}"}

    if not isinstance(spec, dict):
        return {
            "error": "Parsed spec is not a valid OpenAPI/Swagger object"
        }

    # Detect specification version.
    openapi_version = (
        spec.get("openapi")
        or spec.get("swagger")
        or "unknown"
    )

    # Extract metadata.
    info = spec.get("info", {})

    if not isinstance(info, dict):
        info = {}

    title = info.get("title", "Untitled API")
    version = info.get("version", "unknown")

    # Extract base URL.
    base_url = ""

    servers = spec.get("servers", [])

    if isinstance(servers, list) and servers:
        first_server = servers[0]

        if isinstance(first_server, dict):
            base_url = first_server.get("url", "")

    elif "host" in spec:
        schemes = spec.get("schemes", ["https"])

        if not isinstance(schemes, list) or not schemes:
            schemes = ["https"]

        scheme = schemes[0]
        base_path = spec.get("basePath", "")
        host = spec.get("host", "")

        base_url = f"{scheme}://{host}{base_path}"

    # Extract endpoints.
    paths = spec.get("paths", {})

    if not isinstance(paths, dict):
        paths = {}

    endpoints = []

    supported_methods = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
    ]

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        for method in supported_methods:
            operation = path_item.get(method)

            if not isinstance(operation, dict):
                continue

            # Collect operation-level and path-level parameters.
            params = []

            operation_parameters = operation.get("parameters", [])
            path_parameters = path_item.get("parameters", [])

            if not isinstance(operation_parameters, list):
                operation_parameters = []

            if not isinstance(path_parameters, list):
                path_parameters = []

            for parameter in operation_parameters + path_parameters:
                if not isinstance(parameter, dict):
                    continue

                parameter_schema = parameter.get("schema", {})

                if not isinstance(parameter_schema, dict):
                    parameter_schema = {}

                params.append({
                    "name": parameter.get("name"),
                    "in": parameter.get("in"),
                    "required": parameter.get("required", False),
                    "type": (
                        parameter_schema.get("type")
                        if "schema" in parameter
                        else parameter.get("type")
                    ),
                    "description": parameter.get("description", ""),
                })

            # Summarize the request body for OpenAPI 3.x.
            request_body = None
            rb = operation.get("requestBody")

            if isinstance(rb, dict):
                content = rb.get("content", {})

                if isinstance(content, dict):
                    for media_type, media_obj in content.items():
                        if not isinstance(media_obj, dict):
                            continue

                        schema = media_obj.get("schema", {})

                        if not isinstance(schema, dict):
                            schema = {}

                        properties = schema.get("properties", {})

                        if not isinstance(properties, dict):
                            properties = {}

                        request_body = {
                            "media_type": media_type,
                            "required": rb.get("required", False),
                            "properties": list(properties.keys()),
                        }

                        break

            # Safely extract response codes.
            responses = operation.get("responses", {})

            if not isinstance(responses, dict):
                responses = {}

            tags = operation.get("tags", [])

            if not isinstance(tags, list):
                tags = []

            endpoints.append({
                "path": path,
                "method": method.upper(),
                "operation_id": operation.get("operationId"),
                "summary": (
                    operation.get("summary")
                    or operation.get("description", "")
                ),
                "tags": tags,
                "parameters": params,
                "request_body": request_body,
                "responses": list(responses.keys()),
            })

    return {
        "title": title,
        "version": version,
        "openapi_version": openapi_version,
        "base_url": base_url,
        "endpoint_count": len(endpoints),
        "endpoints": endpoints,
    }


# ---------------------------------------------------------------------------
# Tool: fetch_graphql_schema
# ---------------------------------------------------------------------------

# Standard GraphQL introspection query.
_INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types {
      ...FullType
    }
  }
}

fragment FullType on __Type {
  kind
  name
  description
  fields(includeDeprecated: true) {
    name
    description
    args { ...InputValue }
    type { ...TypeRef }
    isDeprecated
    deprecationReason
  }
  inputFields { ...InputValue }
  enumValues(includeDeprecated: true) {
    name
    description
    isDeprecated
  }
  possibleTypes { name }
}

fragment InputValue on __InputValue {
  name
  description
  type { ...TypeRef }
  defaultValue
}

fragment TypeRef on __Type {
  kind
  name
  ofType {
    kind
    name
    ofType {
      kind
      name
      ofType { kind name }
    }
  }
}
"""


def _unwrap_type(type_ref: dict) -> str:
    """
    Recursively unwrap a GraphQL TypeRef into a readable type string.

    Examples:
        String      -> String
        NON_NULL    -> String!
        LIST        -> [String]
        LIST + NON_NULL -> [String!]!
    """
    if not isinstance(type_ref, dict):
        return "Unknown"

    kind = type_ref.get("kind", "")
    name = type_ref.get("name")
    of_type = type_ref.get("ofType")

    if kind == "NON_NULL":
        return f"{_unwrap_type(of_type)}!"

    if kind == "LIST":
        return f"[{_unwrap_type(of_type)}]"

    return name or "Unknown"


def fetch_graphql_schema(
    url: str,
    headers: dict | None = None,
) -> dict:
    """
    Sends a GraphQL introspection query and summarizes the schema.

    Returns a dictionary containing:
        query_type
        mutation_type
        subscription_type
        type_count
        query_count
        mutation_count
        queries
        mutations
        subscriptions
        types

    Errors are returned as dictionaries containing an "error" key.
    """
    if headers is None:
        headers = {}

    request_headers = {
        "Content-Type": "application/json",
        **headers,
    }

    # Send the introspection request.
    try:
        resp = requests.post(
            url,
            json={"query": _INTROSPECTION_QUERY},
            headers=request_headers,
            timeout=20,
        )
        resp.raise_for_status()

    except requests.RequestException as e:
        return {
            "error": (
                "GraphQL introspection request failed: "
                f"{str(e)}"
            )
        }

    # Decode JSON.
    # ValueError also catches invalid-JSON exceptions raised by mocked
    # responses in tests and by JSON decoders.
    try:
        data = resp.json()

    except ValueError as e:
        return {
            "error": (
                "Failed to parse GraphQL response as JSON: "
                f"{str(e)}"
            )
        }

    # A successful JSON decode does not guarantee a valid GraphQL response.
    if not isinstance(data, dict):
        return {
            "error": (
                "Invalid GraphQL response: expected a JSON object"
            )
        }

    # GraphQL can return errors even when the HTTP status is successful.
    if "errors" in data:
        return {
            "error": "GraphQL returned errors",
            "graphql_errors": data["errors"],
        }

    response_data = data.get("data")

    if not isinstance(response_data, dict):
        return {
            "error": "No valid data object found in GraphQL response"
        }

    schema = response_data.get("__schema")

    if not isinstance(schema, dict) or not schema:
        return {
            "error": "No __schema found in introspection response"
        }

    # Extract root operation type names.
    query_type = schema.get("queryType")
    mutation_type = schema.get("mutationType")
    subscription_type = schema.get("subscriptionType")

    query_type_name = (
        query_type.get("name")
        if isinstance(query_type, dict)
        else None
    )

    mutation_type_name = (
        mutation_type.get("name")
        if isinstance(mutation_type, dict)
        else None
    )

    subscription_type_name = (
        subscription_type.get("name")
        if isinstance(subscription_type, dict)
        else None
    )

    all_types = schema.get("types", [])

    if not isinstance(all_types, list):
        return {
            "error": "Invalid GraphQL schema: types must be a list"
        }

    # Skip built-in introspection types.
    builtin_prefixes = ("__",)

    user_types = []
    queries = []
    mutations = []
    subscriptions = []

    for graphql_type in all_types:
        if not isinstance(graphql_type, dict):
            continue

        type_name = graphql_type.get("name", "")
        type_kind = graphql_type.get("kind", "")

        if not isinstance(type_name, str):
            type_name = ""

        if type_name.startswith(builtin_prefixes):
            continue

        fields_raw = graphql_type.get("fields") or []

        if not isinstance(fields_raw, list):
            fields_raw = []

        fields = []

        for field in fields_raw:
            if not isinstance(field, dict):
                continue

            raw_args = field.get("args") or []

            if not isinstance(raw_args, list):
                raw_args = []

            args = []

            for arg in raw_args:
                if not isinstance(arg, dict):
                    continue

                arg_name = arg.get("name", "unknown")
                arg_type = _unwrap_type(arg.get("type", {}))

                args.append(f"{arg_name}: {arg_type}")

            fields.append({
                "name": field.get("name"),
                "type": _unwrap_type(field.get("type", {})),
                "args": args,
                "description": field.get("description", ""),
                "deprecated": field.get("isDeprecated", False),
            })

        enum_values_raw = graphql_type.get("enumValues") or []

        if not isinstance(enum_values_raw, list):
            enum_values_raw = []

        enum_values = [
            enum_value.get("name")
            for enum_value in enum_values_raw
            if isinstance(enum_value, dict)
        ]

        type_entry = {
            "name": type_name,
            "kind": type_kind,
            "description": graphql_type.get("description", ""),
            "fields": fields,
            "enum_values": enum_values,
        }

        # Categorize root operation types separately.
        if type_name == query_type_name:
            queries = fields

        elif type_name == mutation_type_name:
            mutations = fields

        elif type_name == subscription_type_name:
            subscriptions = fields

        else:
            user_types.append(type_entry)

    return {
        "query_type": query_type_name,
        "mutation_type": mutation_type_name,
        "subscription_type": subscription_type_name,
        "type_count": len(user_types),
        "query_count": len(queries),
        "mutation_count": len(mutations),
        "queries": queries,
        "mutations": mutations,
        "subscriptions": subscriptions,
        "types": user_types,
    }