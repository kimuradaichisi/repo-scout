# RepoScout Vision

## Hypothesis

Offloading repository discovery from commercial coding agents to local deterministic tools
and a local model can reduce commercial-model token consumption without reducing implementation
quality.

## Primary target

- Claude token usage reduction: >= 30%
- Target: >= 40%
- Excellent: >= 50%
- Final implementation quality: no regression

## Responsibilities

RepoScout:
- execute repository evidence queries
- preserve source locations
- return compact evidence
- isolate local-model contexts between queries

Commercial coding agent:
- decide what evidence is required
- interpret evidence
- make architectural decisions
- implement or delegate implementation
- directly inspect exact source when behavior depends on implementation details

## Non-goals

RepoScout does not:
- replace Claude Code
- autonomously design architecture
- maintain long-term LLM memory
- infer a full semantic repository model
- build a vector database
- perform implementation in the MVP
