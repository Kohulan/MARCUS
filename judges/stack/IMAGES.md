# Images under test (build "v1")

Copied from production (jarvis) on 2026-11-16 with `docker save | docker load`.
These are the images the running production containers use.

| Image | ID | Built |
|---|---|---|
| marcus-backend:latest | sha256:976396a5e1d2f782450b9f6a1e6d75980e4928cdad8d5c6d0eddc86c958cdf5c | 2026-07-27T10:53:08+02:00 |
| marcus-frontend:latest | sha256:cba87a83c50127caaeeaa751a00292469791fab2997aaf8444ff91b42f8bf543 | 2026-07-27T10:55:21+02:00 |

Production code at that time: commit 4400fb7 (same app code as 1cff8a8).
Local run: CPU only (no GPU on this machine), so absolute times are not production times.

Check on 2026-11-16: the local copies have the same layer list as jarvis
(sha256 of `.RootFS.Layers`: backend f058395e03134ee8, frontend 6e651c9a79407d47).
Local `docker images` shows other IDs and sizes because this machine uses the containerd image store.

## Where the copies run

| Copy | Hardware | Backend | Frontend |
|---|---|---|---|
| local (this machine) | CPU only, 60 cores | http://localhost:19000 | http://localhost:18080 |
| jarvis (project `marcus-judge`) | Tesla V100 shared with production | http://localhost:29000 via SSH tunnel | http://localhost:28080 via SSH tunnel |

Tunnel: `ssh -f -N -L 127.0.0.1:29000:127.0.0.1:19000 -L 127.0.0.1:28080:127.0.0.1:18080 kohulan@jarvis.ian.uni-jena.de`
The jarvis GPU compute mode was changed from Exclusive_Process to Default on 2026-11-16 (by the owner) so both can share it. It resets on reboot.
