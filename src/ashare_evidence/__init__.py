from ashare_evidence.db import init_database


def create_app(*args, **kwargs):
    from ashare_evidence.api import create_app as _create_app

    return _create_app(*args, **kwargs)


__all__ = ["create_app", "init_database"]
