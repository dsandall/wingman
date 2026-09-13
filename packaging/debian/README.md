# Debian package

The `wingman` Debian package supports rootless NetBird instances on Debian and
Ubuntu.

## Runtime integration

The package depends on NetBird, `libcap2-bin`, and polkit. Its maintainer scripts
apply `CAP_NET_ADMIN`, `CAP_NET_RAW`, and `CAP_NET_BIND_SERVICE` to
`/usr/bin/netbird` at install time. `debian/wingman.triggers` registers a dpkg
path trigger for that binary, so its capabilities are restored after any NetBird
package replacement, including unattended upgrades.

It installs `50-wingman-netbird-dns.rules`, authorizing members of the `sudo`
group to configure systemd-resolved's per-interface DNS. Removing `wingman`
clears the capabilities it owns; the polkit rule is removed with the package.

## Build

On Debian trixie or later:

```sh
sudo apt install debhelper dh-python pybuild-plugin-pyproject python3-all \
  python3-hatchling python3-pytest python3-rich python3-typer
dpkg-buildpackage -us -uc -b
```

The resulting `../wingman_<version>_all.deb` is self-contained except for its
APT dependencies.
