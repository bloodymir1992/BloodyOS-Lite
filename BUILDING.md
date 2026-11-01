# Building BloodyOS Lite v0.6 (developer notes)

> **Status:** This is the checked-in live-build configuration, not yet a fully reproducible or independently verified source release. Keep the GitHub Release as a draft until the requirements below are completed.

## Host requirements

Linux host with Docker (privileged container support), sufficient disk space, and the Debian 13 (Trixie) live-build tools. The maintainer used Linux Mint 22.3 on a Z390 computer. The host Mint live-build version was too old; Debian 13 tooling in a Docker container produced the successful ISO.

## Recommended build environment

The maintainer built with a local image named `bloodyos-builder:debian13`, based on `debian:trixie`, including:

```Dockerfile
FROM debian:trixie
RUN apt-get update && apt-get install -y --no-install-recommends \
    live-build debootstrap ca-certificates squashfs-tools xorriso \
    isolinux syslinux-common grub-pc-bin grub-efi-amd64-bin \
    mtools dosfstools curl gnupg
WORKDIR /work
```

This describes the environment used for the earlier build; the container image itself is not included in this repository.

## Source checkout

The `config/` directory contains live-build configuration files, package lists, and files injected into the live filesystem.

The maintainer's successful Docker build was launched **from the directory containing `config/`**:

```sh
docker run --rm --privileged -v "$PWD:/work" -w /work \
  bloodyos-builder:debian13 \
  bash -c 'set -e; lb clean; lb config; lb build'
```

**Important:** The command is historical documentation, **not a guaranteed working build from a fresh clone.** The included configuration was copied from an existing working build tree. Do not overwrite the maintainer's working project or ISO during reproduction experiments.

## Missing prerequisites for a clean build

The Git repository deliberately excludes these prebuilt application executables:

- `config/includes.chroot_after_packages/usr/local/bin/ncspot`
- `config/includes.chroot_after_packages/opt/bloodyos/apps/bloodymusic/ncspot`
- `config/includes.chroot_after_packages/opt/bloodyos/apps/bloodywhats/bloodywhats-engine`

The Go source for the BloodyWhats engine is included in `source/bloodywhats-engine/` with `go.mod` and `go.sum` and was compiled locally by the maintainer, but **binary/source equivalence has not been confirmed**.

The two ncspot paths held a third-party executable; its exact version, acquisition method, and license notice have not yet been recorded. Do not replace it with an unrelated build and claim it reproduces the released ISO.

## License and release verification

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the outstanding licensing and source-distribution checks. Follow each upstream dependency's terms. Do not consider this document or the existence of a buildable Go file a completed source-compliance review.

## Installation

The tested install path uses the graphical Calamares installer, and the maintainer reported an approximately three-minute installation in a virtual machine. Actual times and device compatibility will vary.
