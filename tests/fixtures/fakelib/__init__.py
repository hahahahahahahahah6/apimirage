"""A tiny fake third-party library used to test deprecation detection."""


def new_function(x, y=1):
    """Do the new thing."""
    return (x, y)


def old_function():
    """Deprecated since 1.0: use new_function() instead."""
    return None


def legacy_thing():
    pass


legacy_thing.__deprecated__ = True
