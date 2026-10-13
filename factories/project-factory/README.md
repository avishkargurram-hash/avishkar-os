# Project Factory

## Purpose
Scaffolds brand-new **product repositories** pre-wired to Avishkar OS
(Tryvanta, Humanify OS, GENESIS, Muziclly, AI Atlas, Coupler, and future
products). This is the one factory whose output is not stored inside this
repo — see [ARCHITECTURE.md](../../ARCHITECTURE.md) §2 and §6.

## Responsibilities
- Define the "new product repo" spec: product name, which Chief Domain
  Agents/workflows/starter kit it starts from, deployment target.
- Generate a new repository with Avishkar OS wired in as a dependency (git
  submodule, package, or monorepo-tooling — decided via ADR before this
  factory ships), never as copy-pasted platform code.
- Guarantee the generated repo cannot accidentally import platform
  internals in a way that violates the dependency direction in
  ARCHITECTURE.md §5.

## Architecture
_(To be designed — likely Phase 4.)_ Builds on `starter-kit-factory`
output as its base template, then applies product-specific naming/config.

## Inputs
Product spec: name, starter kit choice, target agents/workflows to include
at creation time.

## Outputs
A new, separate git repository (outside `Avishkar-OS/`) with Avishkar OS
wired in.

## Dependencies
`starter-kit-factory`, `template-factory` (boilerplate config), `core/`
(for the dependency-wiring convention it must follow).

## Examples
_(none yet.)_

## Limitations
Not implemented yet. Zero product repos have been created by this factory
as of the initial scaffold.

## Future improvements
- CLI: `avishkar project new <name> --starter <kit>`.
