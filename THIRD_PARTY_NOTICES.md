# Third-party software notices

BloodyOS Lite v0.6 — BloodyCat Edition includes software from independent developers.

**The project's GNU GPL-3.0-only declaration applies only to original BloodyOS code owned by the project author.** It does not relicense Debian packages, third-party applications, dependencies, images, icons, or other upstream materials.

## Identified components

| Component | Upstream | License |
| --- | --- | --- |
| ncspot (distributed as part of BloodyMusic) | https://github.com/hrkfdn/ncspot | BSD-2-Clause |
| whatsmeow (dependency of BloodyWhats Engine) | https://github.com/tulir/whatsmeow | MPL-2.0 |
| Debian 13 packages, including Openbox, XFCE and Calamares | Their respective upstream projects and Debian package metadata | Various licenses, not covered by the BloodyOS project license |

The exact license texts, copyright notices, corresponding sources, and other redistribution requirements for **all** shipped dependencies must be retained/provided as required by their respective licenses. In particular, the ncspot BSD-2-Clause copyright and license notice must accompany redistributed copies, and the MPL-2.0 requirements applicable to whatsmeow must be respected.

## Release readiness — needs verification

- [x] GitHub repository is private and the v0.6 release remains a draft.
- [x] The custom BloodyWhats Engine Go source is committed at `source/bloodywhats-engine/` and was locally compiled by the project maintainer.
- [ ] Verify that this exact Go source version corresponds to the executable bundled in the ISO.
- [ ] Include ncspot's complete upstream BSD-2-Clause copyright and license notice in the distribution materials.
- [ ] Review third-party artwork, wallpapers, icon themes, fonts, and embedded applications for attribution and redistribution rights.
- [ ] Verify distribution of required source code, build information, and license texts for binaries and their dependencies.
- [ ] Confirm that the source checkout can rebuild the ISO; prebuilt application binaries are currently excluded from Git and their acquisition/build steps are not yet documented.
- [ ] Confirm no private data, sessions, keys, or credentials appear in distributed files or tracked source files.
- [ ] Test the final release ISO and its SHA-256 on the intended hardware.

This document is an inventory and release checklist, **not** a claim of a completed legal compliance audit. Keep the public release unpublished until the outstanding items are resolved.

## Independent services

BloodyWhats is an independent project and is not affiliated with or endorsed by WhatsApp/Meta. BloodyMusic uses a third-party Spotify client and is not affiliated with or endorsed by Spotify.
