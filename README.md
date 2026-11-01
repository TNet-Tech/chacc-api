<p style="font-size:3.2em" align="center">  ChaCC API </p>

<a href="https://chacc.dev" target="blank"><p align="center">
  <img src="chacc_api/assets/chacc-icon.ico" alt="ChaCC API" />
</p></a>



<p align="center"><b>Build modular APIs with independent, pluggable components.</b></p>

<p align="center">ChaCC API is a FastAPI-based platform that lets you build and plug in Python modules like apps. Each module is self-contained – routes, models, logic – and can be installed, updated, or removed without touching the core. </p>

<p align="center"> For the full story, visit <a href="https://chacc.dev" target="blank">chacc.dev</a>.</p>


## Why ChaCC?

- **Modular by design** – Add, remove, or update features without touching the core
- **Plug and play** – Install pre-built modules and get working APIs instantly. No code required
- **Auto database migrations** – Models define their own schema, migrations run automatically
- **Hot reload** – See changes instantly during development
- **Simple deployment** – Package modules as `.chacc` files and deploy anywhere

## Quick Start

```bash
pip install chacc-api
chacc run server --dev
```

Open [http://localhost:8085/docs](http://localhost:8085/docs) to see your API.

## Examples

Official modules maintained by the ChaCC team. All modules are actively being developed – testers welcome:

- [chacc_authentication](https://github.com/tnet-tech/chacc_authentication) – Auth module with JWT, registration, and login
- [chacc_file_manager](https://github.com/tnet-tech/chacc_file_manager) – File management with pluggable adapters. Built-in local storage; bring your own for S3, Google Drive, FTP, or any custom backend.

Build your own module: [Module Development Guide](https://chacc.dev/modules)

## Documentation

Full docs, guides, and API reference: [chacc.dev](https://chacc.dev)

## Contributing

We welcome contributions! Check out [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

## Join the Community
Connect with people that uses ChaCC API on GitHub discussions. [Click here](https://github.com/tnet-tech/chacc-api/discussions)

## Changelog

See what's new in each release: [chacc.dev/changelog](https://chacc.dev/changelog)

[![PyPI](https://img.shields.io/pypi/v/chacc-api?label=PyPI&color=blue)](https://pypi.org/project/chacc-api/)
[![Python](https://img.shields.io/pypi/pyversions/chacc-api?label=Python&color=blue)](https://pypi.org/project/chacc-api/)
[![License](https://img.shields.io/pypi/l/chacc-api?label=License&color=blue)](https://github.com/tnet-tech/chacc-api/blob/main/LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/tnet-tech/chacc-api/ci.yml?label=CI)](https://github.com/tnet-tech/chacc-api/actions/workflows/ci.yml)
[![Star on Github](https://img.shields.io/github/stars/tnet-tech/chacc-api.svg?style=flat-square)](https://github.com/tnet-tech/chacc-api)
[![Discussions](https://img.shields.io/badge/Join-Discussions-blue)](https://github.com/tnet-tech/chacc-api/discussions)

---
## Contributors

ChaCC API exists because people gave their time to make it better.

To everyone who has opened an issue, fixed a bug, improved a sentence of documentation, asked a hard question, or simply tried the beta and told us what broke, thank you so much. You are the reason this project moves forward.

If you'd like to join us, you're welcome here. There is no contribution too small. A typo fix, a clearer error message, a test, a module idea, or a kind word in a discussion all count. Check out [CONTRIBUTING.md](CONTRIBUTING.md) to get started, and know that your name will appear below when you do.

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/jonas1015"><img src="https://avatars.githubusercontent.com/u/54990284?v=4&size=100" width="100px" height="100px" alt="Jonas G Mwambimbi"/><br /><sub><b>Jonas G Mwambimbi</b></sub></a><br /><a href="https://github.com/jonas1015/chacc-api/commits?author=jonas1015" title="Code">💻</a> <a href="#ideas-jonas1015" title="Ideas, Planning, & Feedback">🤔</a> <a href="#infra-jonas1015" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a> <a href="https://github.com/jonas1015/chacc-api/commits?author=jonas1015" title="Tests">⚠️</a> <a href="#design-jonas1015" title="Design">🎨</a> <a href="https://github.com/jonas1015/chacc-api/commits?author=jonas1015" title="Documentation">📖</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/bashirii"><img src="https://avatars.githubusercontent.com/u/104256265?v=4&size=100" width="100px" height="100px" alt="Bashiri Idd"/><br /><sub><b>Bashiri Idd</b></sub></a><br /><a href="https://github.com/jonas1015/chacc-api/commits?author=bashirii" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://linktr.ee/cleven02"><img src="https://avatars.githubusercontent.com/u/168540659?v=4&size=100" width="100px" height="100px" alt="cleven"/><br /><sub><b>cleven</b></sub></a><br /><a href="https://github.com/jonas1015/chacc-api/commits?author=cleven12" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/awodesigns-github"><img src="https://avatars.githubusercontent.com/u/135214966?v=4&size=100" width="100px" height="100px" alt="awodesigns-github"/><br /><sub><b>awodesigns-github</b></sub></a><br /><a href="https://github.com/jonas1015/chacc-api/commits?author=awodesigns-github" title="Code">💻</a></td>
    </tr>
  </tbody>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->
