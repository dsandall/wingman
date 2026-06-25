# Packaging notes

How to make wingman "just work" as a native Arch package: rootless daemons,
user-owned config, persistent across reboot, no `sudo` for everyday commands.

## The model

A wingman instance runs as **your user**, not root:

- Config lives in `~/.config/wingman/<name>` (user-owned).
- Persistence is a `systemctl --user` unit + linger.
- `status` / `peers` / `list` / `up` / `down` all run without `sudo`.

The only privileged need is creating the WireGuard interface, which requires
`CAP_NET_ADMIN`. Instead of running the whole daemon as root, grant that single
capability to the `netbird` binary:

```
sudo setcap cap_net_admin,cap_net_raw+eip /usr/bin/netbird
```

## What the package should do

1. **Ship the pacman hook** `wingman-netbird-setcap.hook` to
   `/usr/share/libalpm/hooks/`. pacman strips file capabilities whenever the
   `netbird` package is reinstalled or upgraded; this hook reapplies them after
   every netbird transaction so the capability never silently disappears.

2. **Apply setcap on first install** via a `.install` `post_install` /
   `post_upgrade` so it's set before the hook ever fires:

   ```sh
   post_install() {
       setcap cap_net_admin,cap_net_raw+eip /usr/bin/netbird
       echo ">>> Enable boot persistence per user with: loginctl enable-linger <user>"
   }
   post_upgrade() { post_install; }
   ```

3. **Depend on** `netbird` and `libcap` (for `setcap`/`getcap`).

`wingman` itself preflights the capability: a rootless `wingman up` aborts early
with the exact `setcap` command if it's missing (via `getcap`), so an unpackaged
install is still self-explanatory.

## First-time user setup (until the AUR package lands)

```fish
sudo setcap cap_net_admin,cap_net_raw+eip /usr/bin/netbird   # one time
wingman up <name> --setup-key <KEY>                          # as your user
sudo loginctl enable-linger $USER                            # persist on boot
```

After that, everyday use needs no `sudo`:

```fish
wingman status <name>
wingman peers <name>
```
