# Packaging notes

How to make wingman "just work" as a native Arch package: rootless daemons,
user-owned config, persistent across reboot, no `sudo` for everyday commands.

## The model

A wingman instance runs as **your user**, not root:

- Config lives in `~/.config/wingman/<name>` (user-owned).
- Persistence is a `systemctl --user` unit + linger.
- `status` / `peers` / `list` / `up` / `down` all run without `sudo`.

The privileged needs are granted narrowly instead of running the daemon as root.
Two are file capabilities on the `netbird` binary, granted together in one
`setcap`:

```
sudo setcap cap_net_admin,cap_net_raw,cap_net_bind_service+eip /usr/bin/netbird
```

1. **Creating the WireGuard interface** requires `CAP_NET_ADMIN`.

2. **Binding the per-instance DNS resolver to port 53** requires
   `CAP_NET_BIND_SERVICE`. systemd-resolved sends queries to the interface IP on
   port 53; a rootless daemon that can't bind 53 falls back to port 5053, which
   resolved never queries, so lookups get connection-refused even though the
   resolver is running.

The third need is **letting the daemon install per-instance DNS** into
systemd-resolved. The daemon asks resolved to set its interface's DNS
server/domains (`org.freedesktop.resolve1.set-*`); polkit denies that to non-root
callers by default, so a rule must authorize it. Without it the tunnel still
comes up but resolved ignores the resolver entirely (`resolvectl status <iface>`
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
       setcap cap_net_admin,cap_net_raw,cap_net_bind_service+eip /usr/bin/netbird
       echo ">>> Enable boot persistence per user with: loginctl enable-linger <user>"
   }
   post_upgrade() { post_install; }
   ```

3. **Ship the polkit rule** `wingman-netbird-dns.rules` to
   `/usr/share/polkit-1/rules.d/`. Unlike the file capability, polkit rules
   survive package upgrades, so this needs no reapply hook — just install the
   file (polkitd picks it up automatically).

4. **Depend on** `netbird`, `libcap` (for `setcap`/`getcap`), and `polkit`.

`wingman` itself preflights these: a rootless `wingman up` aborts early with the
exact `setcap` command if `CAP_NET_ADMIN` is missing (via `getcap`), and warns
(without blocking) if DNS won't work — either polkit will reject resolved updates
(via `pkcheck`) or `CAP_NET_BIND_SERVICE` is missing (via `getcap`) — so an
unpackaged install is still self-explanatory.

## First-time user setup (until the AUR package lands)

```fish
sudo setcap cap_net_admin,cap_net_raw,cap_net_bind_service+eip /usr/bin/netbird  # one time
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
