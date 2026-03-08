"""
Security utilities for input sanitization and prompt injection prevention.
"""
import re
from typing import List, Tuple


def sanitize_input(text: str) -> str:
    """
    Sanitize user input to prevent prompt injection attacks.

    Removes or escapes potentially dangerous patterns:
    - System prompts (e.g., "Ignore previous instructions")
    - Code execution attempts
    - Special command sequences

    Args:
        text: Raw user input

    Returns:
        Sanitized text safe for LLM processing
    """
    if not text:
        return ""

    # Remove null bytes
    text = text.replace("\x00", "")

    # List of dangerous patterns that might indicate prompt injection
    dangerous_patterns = [
        r"(?i)ignore\s+(previous|all|above)\s+instructions?",
        r"(?i)forget\s+(previous|all|above)",
        r"(?i)system\s*:",
        r"(?i)assistant\s*:",
        r"(?i)you\s+are\s+now",
        r"(?i)new\s+instructions?\s*:",
        r"(?i)disregard\s+(previous|all)",
        r"(?i)override\s+(previous|all)",
        r"(?i)pretend\s+you\s+are",
        r"(?i)act\s+as\s+if",
        r"(?i)roleplay",
        r"(?i)execute\s+(command|code|script)",
        r"(?i)run\s+(command|code|script)",
        r"(?i)<script",
        r"(?i)javascript\s*:",
        r"(?i)eval\s*\(",
        r"(?i)exec\s*\(",
    ]

    # Remove dangerous patterns
    sanitized = text
    for pattern in dangerous_patterns:
        sanitized = re.sub(pattern, "", sanitized)

    # Remove markdown formatting that might interfere with embeddings
    # Remove markdown bold/italic markers (**text**, *text*, __text__, _text_)
    sanitized = re.sub(r'\*\*([^*]+)\*\*', r'\1',
                       sanitized)  # **text** -> text
    sanitized = re.sub(r'\*([^*]+)\*', r'\1', sanitized)  # *text* -> text
    sanitized = re.sub(r'__([^_]+)__', r'\1', sanitized)  # __text__ -> text
    sanitized = re.sub(r'_([^_]+)_', r'\1', sanitized)  # _text_ -> text

    # Remove excessive whitespace
    sanitized = re.sub(r"\s+", " ", sanitized).strip()

    # Limit length to prevent DoS
    max_length = 2000
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]

    return sanitized


def validate_question(question: str) -> Tuple[bool, str]:
    """
    Validate that the question is safe and well-formed.

    Args:
        question: User question to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not question or not question.strip():
        return False, "Question cannot be empty"

    if len(question) > 2000:
        return False, "Question exceeds maximum length of 2000 characters"

    # Check for suspicious patterns
    suspicious_patterns = [
        r"(?i)(password|secret|key|token|credential)",
        r"(?i)(delete|drop|remove|truncate)\s+(all|everything|database)",
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, question):
            # Log but don't block - might be legitimate questions about security
            pass

    return True, ""


def extract_sources_from_chunks(chunks: List[dict]) -> List[str]:
    """
    Extract unique source file paths from retrieved chunks.

    Args:
        chunks: List of chunk dictionaries with metadata

    Returns:
        List of unique source file paths
    """
    sources = set()
    for chunk in chunks:
        if "source" in chunk.get("payload", {}):
            source = chunk["payload"]["source"]
            if source:
                sources.add(source)
    return sorted(list(sources))
