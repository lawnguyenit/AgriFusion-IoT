def materialize_dataset_views(*args, **kwargs):
    from .pipelines.materialize import materialize_dataset_views as _materialize_dataset_views

    return _materialize_dataset_views(*args, **kwargs)


__all__ = ["materialize_dataset_views"]
