"""Deterministic HTTP execution and assertions; no retries or redirects."""

import asyncio
import json
import math
import os
import re
from time import perf_counter
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

MAX_RESPONSE = 256 * 1024
SENSITIVE = re.compile(r"password|secret|token|authorization|cookie|api[_-]?key", re.I)


class JsonCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pointer: str = Field(max_length=200)
    expected: JsonValue


class ExecutionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path_params: dict[str, str] = Field(default_factory=dict, max_length=30)
    query_params: dict[str, str] = Field(default_factory=dict, max_length=30)
    body: JsonValue = None
    expected_status: int = Field(default=200, ge=100, le=599)
    checks: list[JsonCheck] = Field(default_factory=list, max_length=20)
    timeout_seconds: float = Field(default=5, ge=0.1, le=10, allow_inf_nan=False)

    @model_validator(mode="after")
    def bounded_input(self):
        try:
            encoded = json.dumps(self.model_dump(), ensure_ascii=False, allow_nan=False).encode('utf-8')
        except (ValueError, UnicodeError):
            raise ValueError('Request must contain valid finite JSON values') from None
        if len(encoded) > 64 * 1024:
            raise ValueError('Execution input exceeds 64 KiB')
        for check in self.checks:
            if (check.pointer and not check.pointer.startswith('/')) or re.search(r'~(?![01])', check.pointer):
                raise ValueError('JSON Pointer must be empty or begin with /')
        return self


def origin(url: httpx.URL) -> str:
    port = url.port or (443 if url.scheme == 'https' else 80)
    return f'{url.scheme}://{url.host}:{port}'


def build_url(base_url: str, operation: dict, payload: ExecutionInput) -> str:
    base = httpx.URL(base_url)
    allowed = os.getenv('QUALITYOPS_ALLOWED_ORIGINS', 'http://127.0.0.1:9000').split(',')
    try:
        allowed_origins = {origin(httpx.URL(value.strip())) for value in allowed if value.strip()}
    except httpx.InvalidURL:
        raise ValueError('QUALITYOPS_ALLOWED_ORIGINS 配置格式无效。') from None
    if origin(base) not in allowed_origins:
        raise ValueError('目标服务未获准执行，请配置后端 QUALITYOPS_ALLOWED_ORIGINS。')
    if operation['method'] not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'}:
        raise ValueError('当前不支持此 HTTP 方法。')
    path = operation['path']
    names = set(re.findall(r'\{([^{}]+)\}', path))
    if names != set(payload.path_params):
        raise ValueError('路径参数必须与接口路径中的占位符完全匹配。')
    for name, value in payload.path_params.items():
        if not value or value in {'.', '..'}:
            raise ValueError('路径参数不能为空或路径跳转符。')
        path = path.replace('{' + name + '}', quote(value, safe=''))
    if any(segment in {'.', '..'} for segment in path.split('/')) or '?' in path or '#' in path:
        raise ValueError('接口路径包含不支持的跳转、查询或片段。')
    if payload.body is not None and operation['method'] in {'GET', 'HEAD', 'OPTIONS'}:
        raise ValueError('当前此 HTTP 方法不接受 JSON 请求体。')
    for parameter in operation.get('parameters', []):
        if parameter.get('required') and parameter.get('in') == 'query' and parameter['name'] not in payload.query_params:
            raise ValueError(f"缺少必填查询参数：{parameter['name']}")
        if parameter.get('required') and parameter.get('in') in {'header', 'cookie'}:
            raise ValueError('当前阶段不支持必填 Header/Cookie 参数。')
    security = operation.get('security', [])
    if security and not any(not requirement for requirement in security):
        raise ValueError('当前阶段暂不支持需要认证的接口。')
    body_definition = operation.get('request_body')
    if body_definition and body_definition.get('required') and payload.body is None:
        raise ValueError('此接口需要 JSON 请求体。')
    if payload.body is not None and (not body_definition or 'application/json' not in body_definition.get('content', {})):
        raise ValueError('此接口未声明 application/json 请求体。')
    url = str(base).rstrip('/') + path
    if origin(httpx.URL(url)) != origin(base):
        raise ValueError('解析后的请求地址超出项目范围。')
    return url


def redact(value, depth=0):
    if depth > 32:
        return '[depth limit]'
    if isinstance(value, dict):
        return {redact(key): '[REDACTED]' if SENSITIVE.search(key) else redact(item, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, depth + 1) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return '[non-finite]'
    if isinstance(value, str):
        return value.encode('utf-8', errors='replace').decode('utf-8')
    return value


def json_pointer(value, pointer):
    if not pointer:
        return value
    for token in pointer[1:].split('/'):
        if re.search(r'~(?![01])', token):
            raise KeyError(pointer)
        token = token.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', token):
                raise KeyError(pointer)
            value = value[int(token)]
        elif isinstance(value, dict):
            value = value[token]
        else:
            raise KeyError(pointer)
    return value


def json_equal(actual, expected):
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(json_equal(actual[key], expected[key]) for key in actual)
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(json_equal(a, b) for a, b in zip(actual, expected))
    return actual == expected


async def perform(url: str, operation: dict, payload: ExecutionInput, transport=None) -> dict:
    started = perf_counter()
    result = {'status': 'error', 'response': None, 'assertions': [], 'error': None}
    try:
        async with asyncio.timeout(payload.timeout_seconds):
            async with httpx.AsyncClient(timeout=payload.timeout_seconds, follow_redirects=False, trust_env=False, transport=transport) as client:
                options = {'params': payload.query_params, 'headers': {'Accept': 'application/json', 'Accept-Encoding': 'identity'}}
                if payload.body is not None:
                    options['json'] = payload.body
                async with client.stream(operation['method'], url, **options) as response:
                    if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                        raise ValueError('当前仅支持未压缩响应，目标服务忽略了 identity 编码请求。')
                    chunks = []
                    size = 0
                    async for chunk in response.aiter_bytes(chunk_size=16384):
                        size += len(chunk)
                        if size > MAX_RESPONSE:
                            raise ValueError('响应超过 256 KiB，已停止读取。')
                        chunks.append(chunk)
                    raw = b''.join(chunks)
                    text = raw.decode('utf-8', errors='replace')
                    is_json = True
                    try:
                        body = json.loads(text)
                    except (ValueError, RecursionError):
                        body = text
                        is_json = False
                    assertions = [{'type': 'status', 'expected': payload.expected_status, 'actual': response.status_code, 'passed': response.status_code == payload.expected_status}]
                    for check in payload.checks:
                        try:
                            if not is_json:
                                raise KeyError(check.pointer)
                            actual = json_pointer(body, check.pointer)
                            passed = json_equal(actual, check.expected)
                            error = None
                        except (KeyError, IndexError, ValueError, TypeError):
                            actual, passed, error = None, False, '响应不是 JSON 或指针不存在。'
                        sensitive = bool(SENSITIVE.search(check.pointer))
                        assertions.append({'type': 'json_equals', 'pointer': check.pointer, 'expected': '[REDACTED]' if sensitive else check.expected, 'actual': '[REDACTED]' if sensitive else actual, 'passed': passed, 'error': error})
                    result.update(status='passed' if all(item['passed'] for item in assertions) else 'failed',
                                  response={'status_code': response.status_code, 'content_type': response.headers.get('content-type', ''), 'body': redact(body), 'is_json': is_json},
                                  assertions=redact(assertions))
    except (TimeoutError, httpx.TimeoutException):
        result['error'] = '请求超时；未自动重试，请确认服务端状态后再执行。'
    except httpx.RequestError:
        result['error'] = '无法连接目标服务或响应协议异常；未自动重试。'
    except ValueError as error:
        result['error'] = str(error)
    result['duration_ms'] = round((perf_counter() - started) * 1000)
    return result
