"""avishkar_scientist -- Scientist OS, the autonomous scientific research
subsystem of Avishkar OS. See ../../CONTRACT.md and ../../README.md.

Layering (each layer only imports the ones above it):

    domain, config                      -- enums, depth profiles, settings
    storage (db, migrations, objects)   -- Postgres truth + content-addressed files
    events, orchestration               -- persisted events, durable task engine
    models, tools                       -- tiered model router, tool registry
    evidence                            -- claims, provenance, independence, RQS
    agents                              -- task handlers (workers' bodies)
    core, termination, verdict, reports -- Scientist Core, stop rules, verdict
    api, integrations, cli              -- REST+SSE, Layla, entrypoints
"""

__version__ = "1.0.0"
