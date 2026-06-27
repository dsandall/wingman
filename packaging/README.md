# Packaging notes

How to make wingman "just work" as a native Arch package: rootless daemons,
user-owned config, persistent across reboot, no `sudo` for everyday commands.

## The model

A wingman instance runs as **your user**, not root:

- Config lives in `~/.config/wingman/<name>` (user-owned).
- Persistence is a `systemctl --user` unit + linger.
- `status` / `peers` / `list` / `up` / `down` all run without `sudo`.

There are two privileged needs, both granted narrowly instead of running the
daemon as root:

1. **Creating the WireGuard interface** requires `CAP_NET_ADMIN`. Grant that
   single capability to the `netbird` binary:

   ```
   sudo setcap cap_net_admin,cap_net_raw+eip /usr/bin/netbird
   ```

2. **Installing per-instance DNS** through systemd-resolved. The daemon asks
   resolved to set its interface's DNS server/domains
   (`org.freedesktop.resolve1.set-*`); polkit denies that to non-root callers by
   default, so a rule must authorize it. Without it the tunnel still comes up but
   NetBird name resolution silently doesn't work (`resolvectl status <iface>`
   shows `Current Scopes: none`). Ship a polkit rule granting the `wheel` group
   those actions:

   ```
   /usr/share/polkit-1/rules.d/50-wingman-netbird-dns.rules
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

3. **Ship the polkit rule** `wingman-netbird-dns.rules` to
   `/usr/share/polkit-1/rules.d/`. Unlike the file capability, polkit rules
   survive package upgrades, so this needs no reapply hook — just install the
   file (polkitd picks it up automatically).

4. **Depend on** `netbird`, `libcap` (for `setcap`/`getcap`), and `polkit`.

`wingman` itself preflights both: a rootless `wingman up` aborts early with the
exact `setcap` command if `CAP_NET_ADMIN` is missing (via `getcap`), and warns
(without blocking) if systemd-resolved will reject its DNS (via `pkcheck`), so an
unpackaged install is still self-explanatory.

## First-time user setup (until the AUR package lands)

```fish
sudo setcap cap_net_admin,cap_net_raw+eip /usr/bin/netbird   # one time
sudo install -Dm644 packaging/arch/wingman-netbird-dns.rules \
    /etc/polkit-1/rules.d/50-wingman-netbird-dns.rules       # one time (DNS)
wingman up <name> --setup-key <KEY>                          # as your user
sudo loginctl enable-linger $USER                            # persist on boot
```

After that, everyday use needs no `sudo`:

```fish
wingman status <name>
wingman peers <name>
```
