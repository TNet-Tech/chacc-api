# Vendored scripts

Third-party files served by the console. Load them on demand; don't edit them.

| File | Package | Version | License |
| --- | --- | --- | --- |
| `mermaid-11.17.2.min.js` | [mermaid](https://www.npmjs.com/package/mermaid) (`dist/mermaid.min.js`) | 11.17.2 | MIT (`mermaid-LICENSE.txt`) |

The version is in the file name so browsers fetch a new file after an upgrade.
To upgrade: `npm pack mermaid@<version>`, copy `package/dist/mermaid.min.js` here
under the new name, and update `MERMAID_URL` in `../console/markdown.js` and this table.
