# QIDI Q2 production Sweep-only package.
#
# The APA pipeline owns its result JSON and Orca output.  Upstream single-PA
# profile management is intentionally not exposed in this production package.


class ProfileMixin:
    def _register_profile_commands(self):
        pass

    def _load_profiles(self):
        return {}
