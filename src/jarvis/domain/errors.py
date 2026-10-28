"""User-visible service failures; adapters sanitize provider details before raising."""
class ServiceError(RuntimeError):
    pass
