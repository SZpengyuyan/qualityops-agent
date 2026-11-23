"""Bounded, offline OpenAPI import. Schema references remain symbolic."""

import json
import math
import re
from urllib.parse import unquote
from uuid import NAMESPACE_URL, uuid5

from openapi_spec_validator import OpenAPIV30SpecValidator, OpenAPIV31SpecValidator

MAX_BYTES = 1024 * 1024
MAX_OPERATIONS = 500
METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


class ImportError(ValueError):
    pass


def pointer(spec: dict, reference: str):
    if not isinstance(reference, str) or not reference.startswith("#/"):
        raise ImportError("仅支持文档内部 #/ 引用，不支持外部文件、URL 或锚点引用。")
    target = spec
    try:
        for token in unquote(reference[2:]).split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(target, list):
                if not re.fullmatch(r"0|[1-9][0-9]*", token):
                    raise KeyError(token)
                target = target[int(token)]
            else:
                target = target[token]
    except (KeyError, IndexError, TypeError, ValueError):
        raise ImportError("文档存在无法解析的内部引用。") from None
    return target


def resolve(spec: dict, value: dict) -> dict:
    seen = set()
    while "$ref" in value:
        reference = value["$ref"]
        if reference in seen:
            raise ImportError("参数、路径、请求体或响应中存在循环引用。")
        seen.add(reference)
        target = pointer(spec, reference)
        if not isinstance(target, dict):
            raise ImportError("引用目标必须是对象。")
        value = {**target, **{key: item for key, item in value.items() if key != "$ref"}}
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ImportError("JSON 中存在重复字段，请先消除重复定义。")
        result[key] = value
    return result


def reject_constant(value):
    raise ImportError("JSON 不支持 NaN 或 Infinity。")


def parse_openapi(content: str) -> tuple[dict, list[dict]]:
    try:
        size = len(content.encode("utf-8"))
    except UnicodeEncodeError:
        raise ImportError("文档包含无效的 Unicode 字符。") from None
    if size > MAX_BYTES:
        raise ImportError("文档大小不能超过 1 MiB。")
    try:
        spec = json.loads(content, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except ImportError:
        raise
    except (ValueError, RecursionError):
        raise ImportError("请输入有效的 JSON 文档；当前不支持 YAML。") from None
    if not isinstance(spec, dict) or not re.fullmatch(r"3\.(0|1)\.\d+", str(spec.get("openapi", ""))):
        raise ImportError("当前仅支持 OpenAPI 3.0.x / 3.1.x JSON 文档。")

    # Bound traversal before invoking a third-party validator; no external resources.
    stack = [(spec, 0)]
    nodes = 0
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if depth > 48 or nodes > 50000:
            raise ImportError("文档嵌套过深或结构过于复杂。")
        if isinstance(node, float) and not math.isfinite(node):
            raise ImportError("JSON 数值超出可支持范围。")
        if isinstance(node, str):
            try:
                node.encode("utf-8")
            except UnicodeEncodeError:
                raise ImportError("文档包含无效的 Unicode 字符。") from None
        if isinstance(node, dict):
            if any(key in node for key in ("$id", "$schema", "$dynamicRef", "$recursiveRef", "jsonSchemaDialect")):
                raise ImportError("当前不支持自定义 Schema 方言、资源标识或动态引用。")
            if "$ref" in node:
                pointer(spec, node["$ref"])
            stack.extend((value, depth + 1) for value in node.values())
            stack.extend((key, depth + 1) for key in node)
        elif isinstance(node, list):
            stack.extend((value, depth + 1) for value in node)

    try:
        validator = OpenAPIV30SpecValidator if spec["openapi"].startswith("3.0.") else OpenAPIV31SpecValidator
        validator(spec).validate()
    except Exception:
        raise ImportError("OpenAPI 规范校验失败，请检查 info、paths、参数及响应定义。") from None

    operations = []
    for path, raw_path_item in spec.get("paths", {}).items():
        if path.startswith("x-"):
            continue
        path_item = resolve(spec, raw_path_item)
        if "$ref" in raw_path_item and any(key in raw_path_item for key in METHODS | {"parameters", "servers"}):
            raise ImportError("当前不支持 Path Item 的 $ref 与操作字段混用。")
        for method, operation in path_item.items():
            if method not in METHODS:
                continue
            parameters = {}
            for parameter in path_item.get("parameters", []) + operation.get("parameters", []):
                parameter = resolve(spec, parameter)
                parameters[(parameter["name"], parameter["in"])] = parameter
            operations.append({
                "id": str(uuid5(NAMESPACE_URL, f"{method}:{path}")),
                "method": method.upper(), "path": path,
                "operation_id": operation.get("operationId"),
                "summary": operation.get("summary", ""),
                "description": operation.get("description", ""),
                "tags": operation.get("tags", []),
                "deprecated": operation.get("deprecated", False),
                "parameters": list(parameters.values()),
                "request_body": resolve(spec, operation["requestBody"]) if "requestBody" in operation else None,
                "responses": {code: resolve(spec, response) for code, response in operation.get("responses", {}).items() if not code.startswith("x-")},
                "security": operation.get("security", spec.get("security", [])),
                "servers": operation.get("servers", path_item.get("servers", spec.get("servers", []))),
            })
            if len(operations) > MAX_OPERATIONS:
                raise ImportError("当前每份文档最多支持 500 个接口。")
    if len(json.dumps(operations, ensure_ascii=False).encode("utf-8")) > 4 * MAX_BYTES:
        raise ImportError("解析结果过大，请拆分文档后重试。")
    return spec, operations
