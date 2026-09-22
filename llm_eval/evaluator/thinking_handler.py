"""LLM 思考过程内容提取工具 — 从 cli_subagent 迁移"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CleanedContent:
    """清理后的内容"""
    content: str          # 最终的干净内容(不含思考过程)
    thinking: str         # 提取出的思考过程(可能为空字符串)
    has_thinking: bool    # 是否检测到思考过程


# 嵌入式思考标签的正则模式列表
# 顺序重要：成对标签必须在单标记之前，确保优先匹配完整对
_THINKING_TAG_PATTERNS = [
    # 1. <thinking>...</thinking>（成对，部分模型变体）
    (re.compile(r'<thinking>.*?</thinking>', re.DOTALL | re.IGNORECASE), True),
    # 2. <think\>...</think\>（DeepSeek R1、Qwen/QwQ 本地部署标准标签，成对）
    (re.compile(r'<think\b[^>]*>.*?</think\s*>', re.DOTALL | re.IGNORECASE), True),
    # 3. 仅 </thinking> 或 </think\>（开标签在 chat_template 中，模型只输出闭标签）
    (re.compile(r'.*?</t(?:hink|hinking)\s*>\s*', re.DOTALL | re.IGNORECASE), True),
    # 4. 仅 <thinking> 或 <think\>（闭标签丢失，QwQ-32B 已知问题）
    (re.compile(r'<t(?:hink|hinking)\b[^>]*>.*', re.DOTALL | re.IGNORECASE), True),
    # 5. 思考：\n...（QianWen 中文模式）- 匹配到下一个空行或结尾
    (re.compile(r'思考[：:]\s*\n(.*?)(?=\n\n|\Z)', re.DOTALL), True),
]


def strip_embedded_thinking(content: str) -> Tuple[str, str]:
    """从文本内容中移除嵌入的思考标签,返回(清理后内容, 思考内容)."""
    if not content:
        return content, ""

    extracted_thinking_parts = []
    cleaned = content

    for pattern, _ in _THINKING_TAG_PATTERNS:
        matches = pattern.findall(cleaned)
        if matches:
            for match in matches:
                text = match.strip() if isinstance(match, str) else str(match).strip()
                if text:
                    extracted_thinking_parts.append(text)
            cleaned = pattern.sub('', cleaned)

    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()

    thinking = '\n\n'.join(extracted_thinking_parts)
    if thinking:
        logger.debug("Stripped embedded thinking: %d chars thinking, %d chars content",
                     len(thinking), len(cleaned))
    return cleaned, thinking


# ---------------------------------------------------------------------------
# 自由推理文本剥离
# ---------------------------------------------------------------------------

_REASONING_START_PATTERNS = [
    re.compile(r'^(用户要求|我需要|让我|分析一下|我来|首先|我来分析|分析如下|考虑到)'),
    re.compile(r'^(The user|Based on|I need|Let me|First|I should|Let me analyze)', re.IGNORECASE),
    re.compile(r'^根据(提供的|核心|上述|题目|用户|已有|已知|网络)'),
    re.compile(r'^(好的[，,]|嗯[，,]|OK[，,])'),
]


def strip_free_form_thinking(content: str) -> str:
    """剥离LLM响应中的自由推理文本，保留实际结果。"""
    if not content:
        return content

    content, extracted_thinking = strip_embedded_thinking(content)

    has_thinking = bool(extracted_thinking) or any(
        p.match(content.strip()) for p in _REASONING_START_PATTERNS
    )

    if not has_thinking:
        return content

    blocks = list(re.finditer(r'```.*?\n(.*?)\n```', content, re.DOTALL))

    if blocks:
        last_block = blocks[-1]
        last_block_content = last_block.group(1).strip()
        after_last_block = content[last_block.end():].strip()

        if after_last_block:
            return after_last_block
        else:
            return last_block_content

    lines = content.split('\n')
    boundary_index = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or i < 3:
            continue

        if stripped.startswith('#'):
            boundary_index = i
            break

        if stripped.startswith('**'):
            boundary_index = i
            break

        if stripped.startswith('[') and not stripped.startswith('[根据') and not stripped.startswith('[示例'):
            rest = content[content.index(stripped):]
            balanced = _balanced_bracket_extract(rest, 0)
            if balanced:
                try:
                    json.loads(balanced)
                    boundary_index = i
                    break
                except (json.JSONDecodeError, ValueError):
                    pass

    if boundary_index is not None and boundary_index > 0:
        return '\n'.join(lines[boundary_index:]).strip()

    return content


# ---------------------------------------------------------------------------
# 混合文本 JSON 数组提取
# ---------------------------------------------------------------------------


def _balanced_bracket_extract(text: str, start: int, open_char='[', close_char=']') -> Optional[str]:
    """从指定位置开始，用栈匹配平衡的括号对，提取平衡的子串。"""
    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == '\\':
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def extract_json_array_from_response(response: str) -> Optional[List]:
    """从可能包含自由推理文本的LLM响应中提取JSON数组。"""
    if not response:
        return None

    try:
        result = json.loads(response.strip())
        if isinstance(result, list):
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    json_blocks = list(re.finditer(r'```(?:json)?\s*\n(.*?)\n```', response, re.DOTALL))
    for match in reversed(json_blocks):
        try:
            result = json.loads(match.group(1).strip())
            if isinstance(result, list):
                return result
        except (json.JSONDecodeError, ValueError):
            continue

    for i in range(len(response) - 1, -1, -1):
        if response[i] == '[':
            balanced = _balanced_bracket_extract(response, i)
            if balanced:
                try:
                    result = json.loads(balanced)
                    if isinstance(result, list):
                        return result
                except (json.JSONDecodeError, ValueError):
                    continue

    for i in range(len(response) - 1, -1, -1):
        if response[i] == '{':
            balanced = _balanced_bracket_extract(response, i, open_char='{', close_char='}')
            if balanced:
                try:
                    result = json.loads(balanced)
                    if isinstance(result, dict):
                        tasks = result.get("atomic_tasks", [])
                        if isinstance(tasks, list):
                            return tasks
                except (json.JSONDecodeError, ValueError):
                    continue

    return None


# ---------------------------------------------------------------------------
# 结构化 API 响应提取
# ---------------------------------------------------------------------------


def extract_openai_compatible(result: Dict[str, Any]) -> CleanedContent:
    """从OpenAI兼容格式响应中提取内容,分离思考过程。"""
    thinking = ""
    content = ""

    try:
        message = result["choices"][0]["message"]
        content = message.get("content", "")
        thinking = message.get("reasoning_content", "")
    except (KeyError, IndexError, TypeError):
        content = ""

    cleaned_content, embedded_thinking = strip_embedded_thinking(content)
    if embedded_thinking:
        parts = [p for p in [embedded_thinking, thinking] if p]
        thinking = '\n\n'.join(parts)

    return CleanedContent(
        content=cleaned_content,
        thinking=thinking,
        has_thinking=bool(thinking)
    )


def extract_anthropic_compatible(result: Dict[str, Any]) -> CleanedContent:
    """从Anthropic兼容格式响应中提取内容,分离思考过程。"""
    thinking_parts = []
    text_parts = []

    content_list = result.get("content", [])
    if not isinstance(content_list, list):
        content_str = str(content_list) if content_list else ""
        cleaned, thinking = strip_embedded_thinking(content_str)
        return CleanedContent(content=cleaned, thinking=thinking, has_thinking=bool(thinking))

    for block in content_list:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type", "")

        if block_type == "thinking":
            thinking_text = block.get("thinking", "")
            if thinking_text:
                thinking_parts.append(thinking_text)
        elif block_type == "text":
            text = block.get("text", "")
            if text:
                text_parts.append(text)

    content = "\n\n".join(text_parts)

    cleaned_content, embedded_thinking = strip_embedded_thinking(content)
    if embedded_thinking:
        thinking_parts.insert(0, embedded_thinking)

    thinking = "\n\n".join(thinking_parts)

    return CleanedContent(
        content=cleaned_content,
        thinking=thinking,
        has_thinking=bool(thinking)
    )


def extract_qianwen_dashscope(result: Dict[str, Any]) -> CleanedContent:
    """从QianWen DashScope格式响应中提取内容,分离思考过程。"""
    thinking = ""
    content = ""

    try:
        output = result["output"]
        content = output.get("text", "")
        thinking = output.get("reasoning_content", "")
    except (KeyError, TypeError):
        content = ""

    cleaned_content, embedded_thinking = strip_embedded_thinking(content)
    if embedded_thinking:
        parts = [p for p in [embedded_thinking, thinking] if p]
        thinking = '\n\n'.join(parts)

    return CleanedContent(
        content=cleaned_content,
        thinking=thinking,
        has_thinking=bool(thinking)
    )
