"""Strict whole-value references: data substitution only, never code evaluation."""

import copy
import json
import math
import re

from pydantic import Field, ValidationError, model_validator

from app.services.execution import ExecutionInput, SENSITIVE, json_pointer

NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,63}')
REFERENCE = re.compile(r'\{\{([A-Za-z][A-Za-z0-9_]{0,63})\}\}')


def reference(value):
    if not isinstance(value, str):
        return None
    matched = REFERENCE.fullmatch(value)
    if matched:
        return matched.group(1)
    if '{{' in value or '}}' in value:
        raise ValueError('变量引用必须占据整个字段值，例如 {{order_id}}，不支持字符串拼接。')
    return None


def map_values(value, transform, depth=0):
    if depth > 48:
        raise ValueError('流程配置嵌套不能超过 48 层。')
    if isinstance(value, dict):
        if any('{{' in key or '}}' in key for key in value):
            raise ValueError('不支持在 JSON 对象键名中引用变量。')
        return {key: map_values(item, transform, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [map_values(item, transform, depth + 1) for item in value]
    return transform(value)


def reference_names(payload):
    names = set()
    def collect(value):
        name = reference(value)
        if name:
            names.add(name)
        return value
    for value in (payload.path_params, payload.query_params, payload.body, [check.expected for check in payload.checks]):
        map_values(value, collect)
    return names


class CaseExecutionInput(ExecutionInput):
    extract: dict[str, str] = Field(default_factory=dict, max_length=10)

    @model_validator(mode='after')
    def validate_flow(self):
        reference_names(self)
        for name, pointer in self.extract.items():
            if not NAME.fullmatch(name):
                raise ValueError('变量名需以英文字母开头，仅包含字母、数字和下划线，最长 64 字符。')
            if (pointer and not pointer.startswith('/')) or re.search(r'~(?![01])', pointer) or len(pointer) > 200:
                raise ValueError('提取规则必须使用有效 JSON Pointer，例如 /id。')
            if SENSITIVE.search(name) or SENSITIVE.search(pointer):
                raise ValueError('当前流程变量不支持提取 token/password 等敏感字段；认证能力将在后续阶段实现。')
        return self


def resolve_input(payload, variables):
    resolved_bytes = 0
    def replace(value):
        nonlocal resolved_bytes
        name = reference(value)
        if name and name not in variables:
            raise ValueError('缺少流程变量：' + name)
        # Do not recursively interpret server-provided data as another template.
        resolved = copy.deepcopy(variables[name]) if name else value
        resolved_bytes += len(json.dumps(resolved, ensure_ascii=False, allow_nan=False).encode('utf-8'))
        if resolved_bytes > 64 * 1024:
            raise ValueError('变量替换后的请求输入超过 64 KiB。')
        return resolved
    values = payload.model_dump(exclude={'extract'})
    for field in ('path_params', 'query_params'):
        resolved = map_values(values[field], replace)
        values[field] = {key: value if isinstance(value, str) else json.dumps(value, allow_nan=False) for key, value in resolved.items()}
    values['body'] = map_values(values['body'], replace)
    values['checks'] = [{**check, 'expected': map_values(check['expected'], replace)} for check in values['checks']]
    try:
        return ExecutionInput.model_validate(values)
    except ValidationError:
        # ValidationError text can echo raw request fields into persisted errors.
        raise ValueError('变量替换后的执行配置无效，请检查参数类型、输入大小及字段内容。') from None


def preview_input(payload):
    return resolve_input(payload, {name: 'preview' for name in reference_names(payload)})


def validate_dependencies(payloads):
    available = set()
    for position, payload in enumerate(payloads, 1):
        missing = reference_names(payload) - available
        if missing:
            raise ValueError(f"第 {position} 条用例引用的变量未由前序用例导出：" + ', '.join(sorted(missing)))
        duplicate = set(payload.extract) & available
        if duplicate:
            raise ValueError('同一用例集不允许重复导出变量：' + ', '.join(sorted(duplicate)))
        available.update(payload.extract)


def collect_exports(definitions, result):
    if result['status'] != 'passed' or not definitions:
        return {}
    response = result.get('response')
    if not response or not response.get('is_json'):
        raise ValueError('变量提取失败：响应不是 JSON。')
    values = {}
    for name, pointer in definitions.items():
        try:
            value = json_pointer(response['body'], pointer)
        except (KeyError, IndexError, ValueError, TypeError):
            raise ValueError('变量提取失败：' + name + ' 的 JSON Pointer 不存在。') from None
        if value is None or not isinstance(value, (str, int, float, bool)) or (isinstance(value, float) and not math.isfinite(value)):
            raise ValueError('变量提取失败：' + name + ' 只支持非 null 的字符串、有限数值或布尔值。')
        if value in ('[REDACTED]', '[depth limit]', '[non-finite]'):
            raise ValueError('变量提取失败：不能引用已遮盖或截断的响应值。')
        if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 4096:
            raise ValueError('变量提取失败：' + name + ' 超过 4 KiB。')
        values[name] = value
    return values
