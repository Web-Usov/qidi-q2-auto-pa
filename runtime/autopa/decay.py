# QIDI Q2 production Sweep-only package.
#
# Decay is experimental upstream and is deliberately disabled here.  The class
# exists because the validated AutoPA 0.2.0 core imports DecayMixin.


class DecayMixin:
    def _register_decay_commands(self):
        pass

    def _estimate_decay(self, *args, **kwargs):
        return None
