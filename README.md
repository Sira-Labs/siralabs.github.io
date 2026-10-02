# siralabs.org

Website of [Sira Labs](https://github.com/Sira-Labs): the organisation page and the product
pages (`/arqam/`). Plain HTML and one stylesheet, no build step; served by GitHub Pages from
`main` with the custom domain in `CNAME`. The repository is a project site
(`siralabs.github.io` under the `Sira-Labs` organisation), so it is only reachable at the
custom domain root; keep `CNAME` in place. DNS: four `A`/`AAAA` records for `@` to GitHub
Pages and `www` as a CNAME to `sira-labs.github.io`.

- `index.html` · Sira Labs (night theme)
- `arqam/index.html` · Arqam (sand theme)
- `assets/site.css` · shared styles; `assets/<brand>/` · marks, icons, screenshots and social
  previews, generated in `Sira-Labs/Arqam` by `docs/assets/genlogo.py`

## Projects

The organisation page groups the projects into three tracks of two cards each (`.tracks` in
`site.css`). Each card has a status chip (`.status.preview` for a hosted preview, plain
`.status` for anything earlier) and its links.

| Track | Project | Status | Links |
|---|---|---|---|
| Learning | Suffa | preview | https://suffa.siralabs.org, `Sira-Labs/Suffa` |
| Learning | Arqam | preview | https://arqam-stg.siralabs.org, `/arqam/` (repository private) |
| Data | Tabayyun | preview | https://tabayyun.siralabs.org, `Sira-Labs/Tabayyun` |
| Data | Sahifa | in development | `Sira-Labs/Sahifa`, product page at https://sira-labs.github.io/Sahifa/ |
| Security | Thawr | release candidate | `Sira-Labs/Thawr`, product page at https://sira-labs.github.io/Thawr/ |
| Security | Khandaq | design (R0) | `Sira-Labs/Khandaq` |

The apps run on their own subdomains, not from this repository. When a project changes status
or moves, update its card in `index.html` and this table, and the Arqam page for Arqam. Keep
the same order and wording in the organisation profile (`Sira-Labs/.github`,
`profile/README.md`).

Preview locally: `python3 -m http.server` in this folder, then open http://localhost:8000.
