"""Source-agnostic pipeline: identity resolution, snapshot writing, and the
run orchestrator. Nothing in this package may branch on `source` /
`source_id` -- that is what makes Phase 3's "add a source with one module
plus one registry line" success criterion possible (COLL-06).
"""
