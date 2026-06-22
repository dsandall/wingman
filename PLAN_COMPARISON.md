# Naive Plan vs Twinbird

## What I Was Planning

1. Keep existing `netbird` systemd service running `personal` (via `/var/lib/netbird/thebu/personal.json`)
2. Point a second daemon at `/var/lib/netbird/thebu/softek.json` with a different socket (`unix:///var/run/netbird-softek.sock`)
3. Edit the softek config directly to change the WireGuard interface from `wt0` to `wt1`
4. Write a second systemd unit for the softek instance

## How Twinbird Differs

| Concern | Naive plan | Twinbird |
|---|---|---|
| Config source | Reuses existing profile configs from `/var/lib/netbird/thebu/` | Creates fresh isolated configs in `~/.config/twinbird/<name>/` |
| Service management | Systemd units | PID files with stale-PID detection |
| Interface naming | Manual edit of existing config | Auto-assigned `wt<N>` via `platform.py` |
| Primary install relationship | Builds on top of it; softek config mutation is risky | Fully isolated — runs alongside, doesn't touch primary install |
| Cross-platform | No | Yes (macOS `utun<N>`, Windows TCP sockets) |
| Existing profile reuse | Yes (personal/softek profiles already logged in) | No — requires fresh login per instance |

## Gaps in the Naive Plan

- **Config mutation risk**: editing `softek.json` directly would corrupt the profile for normal `netbird profile use softek` switching
- **No lifecycle management**: no way to check which second-instance daemon is running, restart it, or know its PID
- **DNS collision not considered**: two instances both pushing to systemd-resolved — probably fine since each gets its own interface and domain, but untested

## Open Question for Twinbird

Since the user already has `personal` and `softek` profiles with existing auth, twinbird's fresh-config approach means re-authenticating both. Worth investigating whether twinbird can adopt an existing netbird config rather than starting from scratch.
