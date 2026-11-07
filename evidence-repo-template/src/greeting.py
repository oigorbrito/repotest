#!/usr/bin/env python3
"""Minimal greeting function for smoke-test example."""


def greet(name: str) -> str:
    """Return a predictable greeting for the given name.
    
    Args:
        name: The name to greet. Can be a normal string or empty string.
        
    Returns:
        A greeting string. For non-empty names, returns "Hello, {name}!"
        For empty string, returns "Hello!"
    """
    if not name:
        return "Hello!"
    return f"Hello, {name}!"