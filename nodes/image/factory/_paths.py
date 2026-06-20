"""Path-safety helpers for profile storage (no heavy deps — safe to unit-test)."""
import os


def resolve_profile_path(base, name, suffix=".json"):
    """Resolve a user-supplied profile *name* to an absolute path INSIDE *base*.

    Defends against path traversal: rejects null bytes, and any name that —
    after normalisation — would escape the storage root (e.g. ``../../secret``
    or an absolute path on another drive). Returns the validated absolute path
    (with *suffix* appended). Raises ValueError on any rejected input.
    """
    if name is None:
        raise ValueError("Profile name is required")
    name = str(name)
    if "\x00" in name:
        raise ValueError("Invalid profile name: null byte")

    base_real = os.path.realpath(base)
    candidate = os.path.realpath(os.path.join(base_real, name + suffix))

    # commonpath raises ValueError if the paths share no root (e.g. different
    # Windows drives) — which also means the candidate escaped base; reject it.
    try:
        if os.path.commonpath([base_real, candidate]) != base_real:
            raise ValueError(f"Profile name escapes storage root: {name!r}")
    except ValueError:
        raise ValueError(f"Invalid profile name: {name!r}")

    return candidate
