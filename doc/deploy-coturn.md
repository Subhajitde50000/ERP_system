# Live classroom A/V: TURN relay, ICE configuration & scale notes

The web classroom runs a real WebRTC mesh: every participant holds one
`RTCPeerConnection` per remote peer, with SDP/ICE candidates signalled over the
class WebSocket (`fontend/hooks/use-live-room.ts`). This document covers what
operators must provision around it.

## 1. Why TURN matters here

Out of the box the mesh only gets a public STUN server, so peers behind
symmetric NATs (mobile hotspots, campus/dorm networks, most corporate
firewalls) fail to connect — the symptom is a stream that never starts or
freezes on one side. A TURN server relays media when a direct path cannot be
found. Deploy one coturn instance per campus/region, ideally on a host with a
public IP.

## 2. coturn setup (Docker)

```yaml
# docker-compose.coturn.yml
services:
  coturn:
    image: coturn/coturn:latest
    network_mode: host          # relay needs the host's public IP; no proxy in front
    restart: unless-stopped
    volumes:
      - ./turnserver.conf:/etc/coturn/turnserver.conf:ro
```

```conf
# turnserver.conf — minimal production config
listening-port=3478
tls-listening-port=5349
fingerprint
lt-cred-mech
# Static shared credentials (simplest; rotate by changing both sides):
user=erp-turn:CHANGE_ME_LONG_RANDOM
realm=turn.example.com
# Public IP of the box (required on cloud hosts behind NAT):
external-ip=203.0.113.10
# TLS for turns: (recommended; certbot or mounted certs)
cert=/etc/coturn/cert.pem
pkey=/etc/coturn/pkey.pem
no-cli
# Keep logs useful, disable unused relays:
log-binding-changes
no-tlsv1
no-tlsv1_1
denied-peer-ip=10.0.0.0-10.255.255.255
denied-peer-ip=192.168.0.0-192.168.255.255
min-port=49160
max-port=49200
```

Firewall: open `3478/udp+tcp` and `5349/udp+tcp` (signalling) and the relay
port range `49160-49200/udp` to the world; everything else stays closed.

## 3. Wiring it into the backend

The WebSocket `welcome` frame now carries an `ice_servers` array. Set these
environment variables on **every backend worker**:

```bash
TURN_URL=turn:turn.example.com:3478        # or turns:turn.example.com:5349 for TLS
TURN_USERNAME=erp-turn
TURN_CREDENTIAL=CHANGE_ME_LONG_RANDOM
```

Behaviour (see `app/config.py::ice_servers` and the welcome payload in
`app/routers/online_class.py`):

* all three set → clients receive STUN + authenticated TURN and use it for
  every new peer connection (including reconnects);
* unset → clients keep the built-in STUN fallback; nothing breaks, but peers
  behind strict NAT will not connect. Only a *fully* configured TURN server is
  advertised — a half-configured one would just add failing candidates.

For time-limited REST-auth credentials instead of a static secret, generate
`username = expiry-timestamp:KeyName` / HMAC-SHA1 `credential` upstream and put
them in the same two env vars — no code change needed.

## 4. Verifying

* `trickle-ice` (webrtc.github.io/samples/src/content/peerconnection/trickle-ice):
  add the TURN server with the credentials; you should see a `relay` candidate
  with type `relay`.
* In the live room, browser `about:webrtc` (Firefox) or
  `chrome://webrtc-internals` → selected candidate pair should show `relay`
  when a direct path is impossible.

## 5. Scale limits and the SFU path

A full mesh is n×(n−1) links and each sender uploads n−1 copies of their
stream. Practical ceilings:

| Scenario | Works up to (rough) |
| --- | --- |
| Teacher camera + screen only (students muted) | 25–30 students |
| Students cameras on | ~6–8 participants |

The room UI defaults student cameras off, so teacher-broadcast classes fit the
mesh comfortably. For seminar-style classes where many participants transmit:

1. Keep this codebase's WebSocket signalling (chat/whiteboard/hand/presence)
   as-is — it is transport-agnostic.
2. Put an SFU (LiveKit, mediasoup, Janus, or mediasoup-based services) in
   front for media: each participant uploads one stream to the SFU, which
   fans it out. LiveKit's client SDK can replace `use-live-room.ts`'s
   `RTCPeerConnection` plumbing while the room components keep their UI.
3. `WS_MAX_ROOM_PARTICIPANTS` (backend config) caps room size independently —
   raise it only together with an SFU.

## 6. Mobile

React Native has no WebRTC in this build (Expo Go has no native WebRTC module).
The student InClass screen therefore deep-links to the web classroom
(`/student/online-classes/{id}` in the browser) for audio/video, while the app
keeps chat, raise-hand and attendance. Set:

```bash
EXPO_PUBLIC_WEB_URL=https://erp.example.com     # web console base URL
```

If unset, the button hides and the note explains the limitation.
