from codex_mem.redact import compile_extra_patterns, redact_text


def test_redact_builtin_patterns():
    text = (
        "OpenAI sk-ABC1234567890ABC1234567890ABC123 "
        "GitHub gho_123456789012345678901234567890123456 "
        "AWS AKIA1234567890123456 "
        "JWT Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abcdefghiJ.klmnopqrst"
    )
    redacted = redact_text(text)
    assert "[REDACTED:OPENAI_KEY]" in redacted
    assert "[REDACTED:GITHUB_TOKEN]" in redacted
    assert "[REDACTED:AWS_KEY]" in redacted
    assert "[REDACTED:BEARER]" in redacted


def test_redact_extra_patterns():
    patterns = [r"secret-\d+"]
    compiled = compile_extra_patterns(patterns)
    assert compiled
    redacted = redact_text("token secret-12345", patterns)
    assert "[REDACTED:USER0]" in redacted
