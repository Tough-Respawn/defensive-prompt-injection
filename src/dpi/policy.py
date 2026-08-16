from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from .model import Action, Decision


SENSITIVE_PATH = re.compile(
    r"(?:^|[/\s\"',:{])(?:"
    r"\.aws/credentials|\.ssh(?:[/\s\"',}]|$)|\.gnupg(?:[/\s\"',}]|$)|"
    r"\.kube/config|\.docker/config\.json|"
    r"\.config/(?:gh/hosts\.yml|gcloud/(?:credentials\.db|application_default_credentials\.json))|"
    r"\.azure/(?:accesstokens\.json|azureprofile\.json|msal_token_cache[^/\s\"',}]*)|"
    r"\.dsh/(?:\.credentials\.ya?ml|\.env)(?:[/\s\"',}]|$)|"
    r"(?:id_rsa|id_dsa|id_ecdsa|id_ed25519)(?:\.[a-z0-9_-]+)?(?:[/\s\"',}]|$)|"
    r"(?:\.netrc|\.npmrc|\.pypirc|\.git-credentials)(?:[/\s\"',}]|$)|"
    r"\.env(?:\.[a-z0-9_-]+)?(?:[/\s\"',}]|$)|"
    r"(?:credentials|secrets?)\.(?:json|ya?ml|toml|ini)"
    r")|/proc/(?:self|[0-9]+)/environ|%userprofile%/\.aws/credentials",
    re.IGNORECASE,
)

PROTECTED_PERSISTENCE = re.compile(
    r"(?:^|[/\s\"',:{])(?:"
    r"\.claude/(?:settings(?:\.local)?\.json|rules/|skills/|agents/|commands/|hooks/|projects/[^/]+/memory/)|"
    r"\.codex/(?:config\.toml|hooks\.json|rules/|skills/|plugins/)|"
    r"\.opencode/(?:plugins?/|skills?/|config(?:\.json|\.jsonc|\.toml)?)|"
    r"\.dsh/(?:cordis\.patch\.ya?ml|settings\.ya?ml|profiles/|skills?/|\.agent-presets/|agents\.md)|"
    r"\.(?:deepseek|codewhale)/(?:config\.toml|hooks\.toml|skills?/|agents?/)|"
    r"(?:claude(?:\.local)?|agents(?:\.override)?|memory)\.md(?:[/\s\"',}]|$)|"
    r"\.mcp\.json|\.claude-plugin/(?:plugin|marketplace)\.json|"
    r"\.codex-plugin/plugin\.json|hooks/hooks\.json"
    r")",
    re.IGNORECASE,
)

EXTERNAL_IMAGE = re.compile(
    r"!\[[^\]\r\n]*\]\(\s*<?(?:https?:)?//[^)\r\n>]+>?"
    r"(?:\s+[\"'][^\"'\r\n]*[\"'])?\s*\)"
    r"|<img\b[^>]*\bsrc\s*=\s*[\"']?\s*(?:https?:)?//[^>]*>"
    r"|!\[[^\]\r\n]*\]\[[^\]\r\n]+\]",
    re.IGNORECASE,
)

URL_EXFIL = re.compile(
    r"[?&](?:data|payload|content|secret|token|key|session|conversation|context)=",
    re.IGNORECASE,
)

MUTATING_NAME = re.compile(
    r"^(?i:send|post|create|update|delete|remove|write|edit|upload|publish|deploy|"
    r"execute|run|pay|purchase|invite|message|email|commit|push)(?:[_-]|[A-Z]|$)",
)

SENSITIVE_NAME = re.compile(
    r"(?:credential|secret|private[_-]?key|api[_-]?key|access[_-]?token|environment|environ)",
    re.IGNORECASE,
)


def _normalized(value: Any) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(value)
    return text.lower().replace("\\", "/")


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _strings(nested)


def _target_paths(arguments: dict[str, Any]) -> list[str]:
    targets: list[str] = []
    target_keys = {
        "file_path",
        "filepath",
        "notebook_path",
        "path",
        "target",
        "target_path",
        "filename",
    }
    for key, value in arguments.items():
        if key.lower() in target_keys and isinstance(value, str):
            targets.append(value)

    patch = arguments.get("command")
    if isinstance(patch, str):
        for match in re.finditer(
            r"^(?:\*\*\* (?:Add|Update|Delete) File:|\+\+\+ b/|--- a/)\s*(.+)$",
            patch,
            re.MULTILINE,
        ):
            targets.append(match.group(1).strip())
    return targets


def _shell_category(text: str) -> str | None:
    if SENSITIVE_PATH.search(text):
        return "sensitive-local-data"
    if PROTECTED_PERSISTENCE.search(text):
        return "persistent-security-configuration"
    if re.search(
        r"(?:^|[^a-z0-9_-])(?:curl|wget|nc|ncat|socat|scp|sftp|rsync|ssh|ftp|telnet|http|httpie)"
        r"(?:[^a-z0-9_-]|$)|invoke-(?:webrequest|restmethod)|git\s+push(?:\s|[\"}]|$)",
        text,
        re.IGNORECASE,
    ):
        return "external-network-command"
    if re.search(
        r"(?:^|[^a-z0-9_])(?:env|printenv)(?:[^a-z0-9_]|$)|(?:get-childitem|gci)\s+env:",
        text,
        re.IGNORECASE,
    ):
        return "environment-enumeration"
    if re.search(
        r"\$\{?[a-z0-9_]*(?:token|secret|password|passwd|api_key|private_key|aws_access_key_id)[a-z0-9_]*\}?"
        r"|\$env:[a-z0-9_]*(?:token|secret|password|passwd|api_key|private_key|aws_access_key_id)[a-z0-9_]*",
        text,
        re.IGNORECASE,
    ):
        return "secret-environment-access"
    if re.search(
        r"(?:^|[^a-z0-9_-])(?:python[23]?|node|ruby|perl)\s+(?:-\S*[ce]\S*|--eval)(?:\s|$)"
        r"|(?:^|[^a-z0-9_-])(?:bash|sh|zsh|pwsh|powershell)(?:\.exe)?\s+(?:-c|-command)(?:\s|$)"
        r"|(?:^|[^a-z0-9_-])php\s+-r(?:\s|$)",
        text,
        re.IGNORECASE,
    ):
        return "inline-code-execution"
    if re.search(
        r"rm\s+-(?:r\S*f|f\S*r)|remove-item[^\r\n]*-(?:recurse|r)[^\r\n]*-(?:force|fo)"
        r"|remove-item[^\r\n]*-(?:force|fo)[^\r\n]*-(?:recurse|r)",
        text,
        re.IGNORECASE,
    ):
        return "destructive-shell"
    if re.search(
        r"git\s+(?:reset\s+--hard|clean\s+-\S*f|push[^\r\n]*--force)"
        r"|\b(?:mkfs|diskpart)\b|drop\s+(?:database|table)|truncate\s+table",
        text,
        re.IGNORECASE,
    ):
        return "destructive-state-change"
    if re.search(
        r"dangerously-skip-permissions|bypasspermissions|disableallhooks|chmod\s+(?:-r\s+)?777",
        text,
        re.IGNORECASE,
    ):
        return "security-weakening"
    return None


def _approval(rule_id: str, category: str) -> Decision:
    return Decision(
        effect="require_approval",
        rule_id=rule_id,
        category=category,
        message=(
            "This operation can access sensitive data or cause a high-impact side "
            "effect. Verify that it matches the user's explicit current request."
        ),
    )


def evaluate(action: Action) -> Decision:
    if not action.valid or not action.tool_name or not isinstance(action.arguments, dict):
        return Decision(
            effect="deny",
            rule_id="invalid-action",
            category="unparseable-hook-input",
            message="The hook input could not be parsed safely.",
        )

    text = _normalized(action.arguments)
    name = action.tool_name

    if SENSITIVE_PATH.search(text) or SENSITIVE_NAME.search(name):
        return _approval("sensitive-data", "sensitive-local-data")

    if action.kind == "filesystem.write":
        targets = _target_paths(action.arguments)
        if not targets:
            return _approval("unknown-write-target", "persistent-security-configuration")
        if any(PROTECTED_PERSISTENCE.search(_normalized(target)) for target in targets):
            return _approval("protected-persistence", "persistent-security-configuration")
        if EXTERNAL_IMAGE.search("\n".join(_strings(action.arguments))):
            return _approval("external-image-write", "external-image-persistence")

    if action.kind in {"process.exec", "agent.delegate"}:
        category = _shell_category(text)
        if category:
            prefix = "delegated-" if action.kind == "agent.delegate" else ""
            return _approval(f"{prefix}{category}", f"{prefix}{category}")

    if action.kind == "network.request" and URL_EXFIL.search(text):
        return _approval("url-exfiltration", "possible-url-exfiltration")

    if action.kind == "mcp.call":
        operation = re.split(r"__", name)[-1]
        if URL_EXFIL.search(text):
            return _approval("mcp-url-exfiltration", "mcp-possible-exfiltration")
        if MUTATING_NAME.search(operation):
            return _approval("mutating-mcp-tool", "mutating-mcp-tool")

    if action.kind in {"function.call", "unknown"}:
        if PROTECTED_PERSISTENCE.search(text):
            return _approval("generic-protected-persistence", "persistent-security-configuration")
        if URL_EXFIL.search(text):
            return _approval("generic-url-exfiltration", "possible-url-exfiltration")
        if MUTATING_NAME.search(name):
            return _approval("generic-mutating-tool", "mutating-function-tool")

    if EXTERNAL_IMAGE.search("\n".join(_strings(action.arguments))):
        return _approval("external-image", "external-image-persistence")

    return Decision(
        effect="allow",
        rule_id="no-match",
        category="ordinary-operation",
        message="No deterministic high-risk pattern matched.",
    )
