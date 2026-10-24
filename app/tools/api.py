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
    Fetches and parses an OpenAPI 3.x or Swagger 2.x spec from a URL (JSON or YAML).
    Returns a summarised tool-map so agents can understand an API before calling it:
      { title, version, base_url, endpoints: [{ path, method, summary, parameters }] }
    """
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"error": f"Failed to fetch OpenAPI spec: {str(e)}"}

    content_type = resp.headers.get("Content-Type", "")
    raw = resp.text

    # Parse JSON or YAML
    spec = None
    if "json" in content_type or url.endswith(".json"):
        try:
            spec = json.loads(raw)
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse JSON spec: {str(e)}"}
    else:
        # Try YAML
        if not YAML_AVAILABLE:
            return {"error": "PyYAML is not installed. Install with: pip install PyYAML>=6.0"}
        try:
            spec = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            return {"error": f"Failed to parse YAML spec: {str(e)}"}

    if not isinstance(spec, dict):
        return {"error": "Parsed spec is not a valid OpenAPI/Swagger object"}

    # Detect version
    openapi_version = spec.get("openapi") or spec.get("swagger") or "unknown"

    # Extract metadata
    info = spec.get("info", {})
    title = info.get("title", "Untitled API")
    version = info.get("version", "unknown")

    # Extract base URL
    base_url = ""
    if "servers" in spec and spec["servers"]:
        base_url = spec["servers"][0].get("url", "")
    elif "host" in spec:
        scheme = spec.get("schemes", ["https"])[0]
        base_path = spec.get("basePath", "")
        base_url = f"{scheme}://{spec['host']}{base_path}"

    # Extract endpoints
    paths = spec.get("paths", {})
    endpoints = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in ["get", "post", "put", "patch", "delete", "head", "options"]:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue

            # Parameters: path + query
            params = []
            for p in operation.get("parameters", []) + path_item.get("parameters", []):
                if not isinstance(p, dict):
                    continue
                params.append({
                    "name": p.get("name"),
                    "in": p.get("in"),
                    "required": p.get("required", False),
                    "type": p.get("schema", {}).get("type") if "schema" in p else p.get("type"),
                    "description": p.get("description", ""),
                })

            # Request body summary (OpenAPI 3.x)
            request_body = None
            if "requestBody" in operation:
                rb = operation["requestBody"]
                content = rb.get("content", {})
                for media_type, media_obj in content.items():
                    schema = media_obj.get("schema", {})
                    request_body = {
                        "media_type": media_type,
                        "required": rb.get("required", False),
                        "properties": list(schema.get("properties", {}).keys()) if "properties" in schema else [],
                    }
                    break  # First media type is enough for a summary

            endpoints.append({
                "path": path,
                "method": method.upper(),
                "operation_id": operation.get("operationId"),
                "summary": operation.get("summary") or operation.get("description", ""),
                "tags": operation.get("tags", []),
                "parameters": params,
                "request_body": request_body,
                "responses": list(operation.get("responses", {}).keys()),
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

# Standard GraphQL introspection query
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
    """Recursively unwrap a GraphQL TypeRef to a human-readable string like [String!]."""
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


def fetch_graphql_schema(url: str, headers: dict | None = None) -> dict:
    """
    Sends a GraphQL introspection query to an endpoint and returns the schema
    as structured text (types, queries, mutations, subscriptions).

    Returns:
      { query_type, mutation_type, subscription_type, types: [...], queries: [...], mutations: [...] }
    """
    if headers is None:
        headers = {}

    request_headers = {"Content-Type": "application/json", **headers}

    try:
        resp = requests.post(
            url,
            json={"query": _INTROSPECTION_QUERY},
            headers=request_headers,
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"error": f"GraphQL introspection request failed: {str(e)}"}

    try:
        data = resp.json()
    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse GraphQL response as JSON: {str(e)}"}

    if "errors" in data:
        return {"error": "GraphQL returned errors", "graphql_errors": data["errors"]}

    schema = data.get("data", {}).get("__schema", {})
    if not schema:
        return {"error": "No __schema found in introspection response"}

    query_type_name = (schema.get("queryType") or {}).get("name")
    mutation_type_name = (schema.get("mutationType") or {}).get("name")
    subscription_type_name = (schema.get("subscriptionType") or {}).get("name")

    all_types = schema.get("types", [])

    # Skip built-in introspection types
    BUILTIN_PREFIXES = ("__",)
    SCALAR_NAMES = {"String", "Boolean", "Int", "Float", "ID"}

    user_types = []
    queries = []
    mutations = []
    subscriptions = []

    for t in all_types:
        type_name = t.get("name", "")
        type_kind = t.get("kind", "")

        if type_name.startswith(BUILTIN_PREFIXES):
            continue

        fields_raw = t.get("fields") or []
        fields = []
        for f in fields_raw:
            args = [
                f"{a['name']}: {_unwrap_type(a['type'])}"
                for a in (f.get("args") or [])
            ]
            fields.append({
                "name": f.get("name"),
                "type": _unwrap_type(f.get("type", {})),
                "args": args,
                "description": f.get("description", ""),
                "deprecated": f.get("isDeprecated", False),
            })

        enum_values = [e.get("name") for e in (t.get("enumValues") or [])]

        type_entry = {
            "name": type_name,
            "kind": type_kind,
            "description": t.get("description", ""),
            "fields": fields,
            "enum_values": enum_values,
        }

        # Categorise root operation types separately for quick access
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
