# Changelog

## [0.2.1](https://github.com/LCCC-Tech/rencal/compare/v0.2.0...v0.2.1) (2026-10-08)


### Bug Fixes

* **ci:** publish to TestPyPI before PyPI ([3a7cc39](https://github.com/LCCC-Tech/rencal/commit/3a7cc39e3ff0765ed18dfd8e708eb95394337203))
* **ci:** publish to TestPyPI before PyPI ([#83](https://github.com/LCCC-Tech/rencal/issues/83)) ([2eef335](https://github.com/LCCC-Tech/rencal/commit/2eef33522dfaf7b617882d2b0a9c1dafd95f7c56)), closes [#82](https://github.com/LCCC-Tech/rencal/issues/82)
* **docs:** Fixes broken internal documentation site links ([#85](https://github.com/LCCC-Tech/rencal/issues/85)) ([bb31245](https://github.com/LCCC-Tech/rencal/commit/bb3124518a975d09c4a7b71ebc176db46fc7a8d7)), closes [#84](https://github.com/LCCC-Tech/rencal/issues/84)
* preserve release version marker in uv lock ([c7b28a4](https://github.com/LCCC-Tech/rencal/commit/c7b28a42134cae821b3e0f6b342e9b92c02c21a5))
* preserve release version marker in uv lock ([#91](https://github.com/LCCC-Tech/rencal/issues/91)) ([66940b0](https://github.com/LCCC-Tech/rencal/commit/66940b04b4bee974dd91784780a0cf3db107a304))
* validate documentation links ([#84](https://github.com/LCCC-Tech/rencal/issues/84)) ([c3e50bf](https://github.com/LCCC-Tech/rencal/commit/c3e50bf34671f8b7bef553549d9ac325df67f5f3))


### Documentation

* link API mentions to reference pages ([61e0efa](https://github.com/LCCC-Tech/rencal/commit/61e0efaf4200fb46ff630bdf25f17121aef42f6b))
* link conceptual API mentions ([2caca92](https://github.com/LCCC-Tech/rencal/commit/2caca925fa4d377aefd2a1271937c362693b81eb))
* link tutorial APIs and render lambda math ([dd58c1d](https://github.com/LCCC-Tech/rencal/commit/dd58c1d43397b31a52a2e2b130964a6a31313485))
* render Weibull scale parameter as math ([95893be](https://github.com/LCCC-Tech/rencal/commit/95893be0359a08c8d21f908c3de0b141824db337))

## [0.2.0](https://github.com/LCCC-Tech/rencal/compare/v0.1.1...v0.2.0) (2026-09-21)


### Features

* Adds a site-wide corporate footer matching schemes-register ([f37e7fa](https://github.com/LCCC-Tech/rencal/commit/f37e7fa277046928ebda83df9b08311104df80b3))
* Adds cookie consent banner and toast to docs site ([a78868e](https://github.com/LCCC-Tech/rencal/commit/a78868e91c970daebc3d8177237bbde9f5160715))
* Adds Google Analytics and cookie consent to docs site ([#74](https://github.com/LCCC-Tech/rencal/issues/74)) ([7dfa15c](https://github.com/LCCC-Tech/rencal/commit/7dfa15c6825f688985d19b5ec4016eb1b1829d11))
* Adds Google Analytics tracking to docs site ([6639c62](https://github.com/LCCC-Tech/rencal/commit/6639c6279622b8e4dd4af0a0bff6840db1452b93))
* Adds Privacy and Cookies / Accessibility links to the sidebar ([c38a705](https://github.com/LCCC-Tech/rencal/commit/c38a7050b50b7b8a8b18602b6edc92496e07d42a))
* Adds sitemap.xml generation for docs site ([#57](https://github.com/LCCC-Tech/rencal/issues/57)) ([2f09f93](https://github.com/LCCC-Tech/rencal/commit/2f09f93989adf7ef8540ed3f79155c3fad5fbc4d))
* Makes cookie popup follow the site's light/dark theme ([3626683](https://github.com/LCCC-Tech/rencal/commit/3626683917f24b2cc72b959042ee2d2196c20777))
* Makes cookie toast follow the site's light/dark theme ([93189f0](https://github.com/LCCC-Tech/rencal/commit/93189f091fe3d29100a21aca939a4bdc86946ed2))
* Switches the site font to Atkinson Hyperlegible ([5ec4f7c](https://github.com/LCCC-Tech/rencal/commit/5ec4f7c01878bbfa5a30a40c01cc964238805857))


### Bug Fixes

* Allows imports from source code instead of strictly as package install ([21829ea](https://github.com/LCCC-Tech/rencal/commit/21829eaa3fb59d39491697b899897155d81cc030))
* Allows imports from source code instead of strictly as package install ([#81](https://github.com/LCCC-Tech/rencal/issues/81)) ([da5ea6c](https://github.com/LCCC-Tech/rencal/commit/da5ea6c1c32355a8ec481ace0a91abc74be6d449))
* Centers cookie toast correctly (previous transform was overridden) ([6db1a86](https://github.com/LCCC-Tech/rencal/commit/6db1a860fb0ba0fb673fc0e9637cd817d5e99f67))
* Keeps footer copyright year accurate across long-lived deployments ([09e75b2](https://github.com/LCCC-Tech/rencal/commit/09e75b28687dece42edb5e66e53a826a447df157))
* Moves cookie banner to body to escape sidebar stacking context ([ac378b2](https://github.com/LCCC-Tech/rencal/commit/ac378b2840d78c822426fd615ff22c4dfdb056bc))
* Stacks footer links onto separate rows on mobile ([2e5cb8a](https://github.com/LCCC-Tech/rencal/commit/2e5cb8a516a48c642b591c4e37480b81ebda64c8))
* Stops rejecting cookies from wiping cookies belonging to other apps ([5bc757c](https://github.com/LCCC-Tech/rencal/commit/5bc757cbb779d259a236fc458fdd8348acbd7ef9))


### Reverts

* Removes Privacy and Cookies / Accessibility links from the sidebar ([08a9064](https://github.com/LCCC-Tech/rencal/commit/08a906488f701ca80a5c0128f0e6b71330790ff0))


### Documentation

* Fix documentation site accessibility audit findings ([#68](https://github.com/LCCC-Tech/rencal/issues/68)) ([7582245](https://github.com/LCCC-Tech/rencal/commit/7582245fefc4ef70fa07c13821e25f12f5860460)), closes [#67](https://github.com/LCCC-Tech/rencal/issues/67)
* update PyPI installation quick start ([622f099](https://github.com/LCCC-Tech/rencal/commit/622f099c6878973541ebf7e69efab70cfaf42eeb))

## [0.1.1](https://github.com/LCCC-Tech/rencal/compare/v0.1.0...v0.1.1) (2026-08-19)


### Bug Fixes

* authenticate documentation workflow fetch ([50f4a33](https://github.com/LCCC-Tech/rencal/commit/50f4a3316e233579bf59436a3eee2c54b33c89e1))
* authenticate release ancestry fetch ([0561bd0](https://github.com/LCCC-Tech/rencal/commit/0561bd0634ed3743347ee48847ef9d2f8f737994))
* authenticate release ancestry fetch ([#61](https://github.com/LCCC-Tech/rencal/issues/61)) ([6139625](https://github.com/LCCC-Tech/rencal/commit/613962519c85b3bf3668c63b9bd2e809353a629a))

## 0.1.0 (2026-08-19)


### Documentation

* add contributor licence agreement ([e3a4f96](https://github.com/LCCC-Tech/rencal/commit/e3a4f96cbe424dd0ca88b98a6f8dead055f7ab2c))
* expand developer setup guidance ([fc7e9cb](https://github.com/LCCC-Tech/rencal/commit/fc7e9cb6a7063b19bde290a50a567d75bd8ced26))
* Moves contributor licence agreement higher up within CONTRIBUTING.md ([fd6ecd8](https://github.com/LCCC-Tech/rencal/commit/fd6ecd870b921823c34785c87ac1bbf07bbe79f6))
* prepare public contribution guidance ([68a70a3](https://github.com/LCCC-Tech/rencal/commit/68a70a3695643c54087735dd3bb2e8f6e2aa2f54))
* remove unavailable documentation link ([2e9907b](https://github.com/LCCC-Tech/rencal/commit/2e9907b3303cd1dd27900ef77c2ee56fb8c4efbc))
* restore calibration and sampling examples ([2fe0165](https://github.com/LCCC-Tech/rencal/commit/2fe0165832e49fb0bb0833def3be2f81d41cbffa))
* Updates CONTRIBUTING.md to include commit style and docstring style ([9a2031b](https://github.com/LCCC-Tech/rencal/commit/9a2031b28eb04c85462a9215fdc9c4cc93547eec))

## Changelog

All notable changes to RenCal will be documented in this file by Release Please.

This project follows [Semantic Versioning](https://semver.org/).
