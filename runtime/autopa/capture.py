# QIDI Q2 production Sweep-only package.
#
# The tested AutoPA core keeps capture persistence/indexing in __init__.py.
# Production calibration does not need the optional annotate/delete commands,
# so the mixin intentionally registers nothing.


class CaptureMixin:
    def _register_capture_commands(self):
        pass
