# Build with us

Agents and humans are first-class contributors. Fork the repository, make a useful change, run relevant checks, and submit a pull request. No issue, invitation, CLA, or proposal process is required.

Read [AGENTS.md](AGENTS.md) for the map and [architecture](docs/architecture.md) for the boundaries. Show what changed, why it matters, and how you know it works. A screenshot is useful for desktop behavior; never publish captures containing someone else's private information.

CI checks the package and tests. Ryan is notified to run his local agent. That agent reviews the actual diff and evidence, signs approval for the current head and base commits, and can merge immediately once checks pass. New code requires a new approval. [Governance](docs/governance.md) describes the concrete mechanism and its limits.

For bugs, a command, the versioned JSON error, OS/Python versions, and the narrowest useful reproduction usually suffice. For improvements, ship a working example. For ports, installation and upgrades are part of the feature.

By contributing, you license your contribution under this repository's MIT license.
