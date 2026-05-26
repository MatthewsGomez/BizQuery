"""
Authorization helpers for Lambda functions.

Provides role-based access control utilities used by every Lambda handler
to enforce the permission model defined in the BizQuery design document.
"""

from typing import List


def validate_role(user_role: str, required_roles: List[str]) -> bool:
    """
    Check whether *user_role* is among the *required_roles*.

    Parameters
    ----------
    user_role:
        The role of the authenticated user, extracted from the Cognito JWT
        claim (e.g. ``"owner"`` or ``"employee"``).
    required_roles:
        A list of roles that are permitted to perform the action being
        guarded (e.g. ``["owner"]`` for financial data).

    Returns
    -------
    bool
        ``True`` if *user_role* is in *required_roles*, ``False`` otherwise.

    Examples
    --------
    >>> validate_role("owner", ["owner"])
    True
    >>> validate_role("employee", ["owner"])
    False
    >>> validate_role("employee", ["owner", "employee"])
    True
    >>> validate_role("", ["owner"])
    False
    """
    if not user_role or not required_roles:
        return False
    return user_role in required_roles
