"""Collector plugin package (COLL-06).

Every source implements the `Collector` protocol in `base.py`. `registry.py`
is the single file touched to register a new source -- nothing above
`techtrend/collectors/<source>.py` may branch on source name.
"""
