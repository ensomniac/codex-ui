# Reporting a vulnerability

Use GitHub's private vulnerability reporting for a concrete unintended security issue. Include the affected release, reproduction and impact. Do not include live credentials or private screenshots in public issues.

Full local input and screen access are intentional features. This project runs with the operator's account and OS permissions; it does not provide a sandbox or remote authentication service. Changes that improve correctness or prevent unintended access are welcome. Changes that replace its operating philosophy with speculative permission gates are not.

Release approval credentials stay on the maintainer's machine. CI for pull requests has read-only repository access. The trusted-review workflow does not execute a contributor's code. See [governance](docs/governance.md).
