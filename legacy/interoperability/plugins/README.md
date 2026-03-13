Legacy plugin/helper assets extracted from the hosted root live here.

Boundary rules:
- This folder is an interoperability archive boundary, not an active hosted runtime root.
- Hosted services must consume contract-based shims (`Chummer.Play.Contracts`, `Chummer.Media.Contracts`, `Chummer.Run.Contracts`) instead of source-linking plugin implementations.
- Do not reintroduce `Plugins/` at repo root.
