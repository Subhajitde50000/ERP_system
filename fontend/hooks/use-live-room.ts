"use client";

/**
 * One live-classroom connection shared by the teacher and student rooms.
 *
 * The WebSocket carries presence, chat, raise-hand, whiteboard strokes and
 * WebRTC signalling; media itself flows peer-to-peer in a small mesh (fine
 * for a class-sized room where mostly the teacher broadcasts). Everything
 * here is transport — the room components own the UI.
 *
 * Scale limits (by design, documented for operators): a full mesh is
 * n×(n−1) links and n-1 upload streams per sender, which saturates a typical
 * uplink past ~6–8 active cameras. The room UI keeps students' cameras off
 * by default, so teacher-broadcast classes work well beyond that, but
 * multi-camera classes larger than ~8 participants need an SFU (e.g.
 * LiveKit/mediasoup) in front of this signalling — see doc/deploy-coturn.md.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { refreshAccessToken } from "@/lib/auth";
import { liveRoomUrl } from "@/lib/online-class";

export interface PeerInfo {
  id: string;
  name: string;
  role: string;
}

export interface LiveChatMessage {
  sender_id: string;
  sender_name: string;
  sender_role: string;
  body: string;
}

export interface Stroke {
  color: string;
  points: [number, number][];
}

export interface LiveRoom {
  connected: boolean;
  role: string | null;
  peers: PeerInfo[];
  streams: Record<string, MediaStream>;
  myStream: MediaStream | null;
  chat: LiveChatMessage[];
  raisedHands: string[];
  screenSharerId: string | null;
  strokes: Stroke[];
  mediaError: string | null;
  sendChat: (body: string) => void;
  toggleHand: (raised: boolean) => void;
  toggleMic: () => void;
  toggleCam: () => void;
  micOn: boolean;
  camOn: boolean;
  startScreenShare: () => Promise<void>;
  stopScreenShare: () => void;
  screenSharing: boolean;
  drawStroke: (stroke: Stroke) => void;
  clearBoard: () => void;
  isLargeClass: boolean;
  sfuAvailable: boolean;
}

/**
 * ICE fallback used until the server's welcome frame arrives. The backend can
 * deliver deployment-specific servers (STUN + authenticated TURN relay — see
 * doc/deploy-coturn.md) via the welcome payload's `ice_servers`, which is what
 * gets peers through symmetric NATs and strict firewalls.
 */
const defaultIceServers: RTCIceServer[] = [{ urls: "stun:stun.l.google.com:19302" }];
if (
  typeof process !== "undefined" &&
  process.env.NEXT_PUBLIC_TURN_URL &&
  process.env.NEXT_PUBLIC_TURN_USERNAME &&
  process.env.NEXT_PUBLIC_TURN_CREDENTIAL
) {
  defaultIceServers.push({
    urls: process.env.NEXT_PUBLIC_TURN_URL.split(",").map((u) => u.trim()),
    username: process.env.NEXT_PUBLIC_TURN_USERNAME,
    credential: process.env.NEXT_PUBLIC_TURN_CREDENTIAL,
  });
}
const RTC_CONFIG: RTCConfiguration = { iceServers: defaultIceServers };

export function useLiveRoom(classId: string, onClassEnded?: () => void): LiveRoom {
  const [connected, setConnected] = useState(false);
  const [role, setRole] = useState<string | null>(null);
  const [peers, setPeers] = useState<PeerInfo[]>([]);
  const [streams, setStreams] = useState<Record<string, MediaStream>>({});
  const [myStream, setMyStream] = useState<MediaStream | null>(null);
  const [chat, setChat] = useState<LiveChatMessage[]>([]);
  const [raisedHands, setRaisedHands] = useState<string[]>([]);
  const [screenSharerId, setScreenSharerId] = useState<string | null>(null);
  const [strokes, setStrokes] = useState<Stroke[]>([]);
  const [mediaError, setMediaError] = useState<string | null>(null);
  const [micOn, setMicOn] = useState(true);
  const [camOn, setCamOn] = useState(true);
  const [screenSharing, setScreenSharing] = useState(false);
  const [sfuAvailable, setSfuAvailable] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  // Server-delivered ICE config (welcome frame); null until it arrives.
  const iceServersRef = useRef<RTCIceServer[] | null>(null);
  const pcsRef = useRef<Map<string, RTCPeerConnection>>(new Map());
  const localRef = useRef<MediaStream | null>(null);
  const screenTrackRef = useRef<MediaStreamTrack | null>(null);
  const closedByUser = useRef(false);
  const endedRef = useRef(onClassEnded);
  useEffect(() => {
    endedRef.current = onClassEnded;
  }, [onClassEnded]);

  const send = useCallback((payload: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload));
  }, []);

  // ── WebRTC plumbing ────────────────────────────────────────────────────────

  const attachStream = useCallback((peerId: string, stream: MediaStream) => {
    setStreams((prev) => ({ ...prev, [peerId]: stream }));
  }, []);

  const createPeer = useCallback(
    (peer: PeerInfo, initiator: boolean) => {
      if (pcsRef.current.has(peer.id)) return pcsRef.current.get(peer.id)!;
      const pc = new RTCPeerConnection(iceServersRef.current ? { iceServers: iceServersRef.current } : RTC_CONFIG);
      pcsRef.current.set(peer.id, pc);
      localRef.current?.getTracks().forEach((track) => {
        const sender = pc.addTrack(track, localRef.current!);
        // Adaptive bitrate: cap student video to 150 kbps so multi-student mesh doesn't saturate uplink
        if (track.kind === "video" && sender && sender.getParameters) {
          try {
            const params = sender.getParameters();
            if (params.encodings && params.encodings.length > 0) {
              params.encodings[0].maxBitrate = 150000;
              params.encodings[0].maxFramerate = 15;
              sender.setParameters(params).catch(() => {});
            }
          } catch {
            /* browser without sender parameters */
          }
        }
      });
      const remote = new MediaStream();
      pc.ontrack = (event) => {
        remote.addTrack(event.track);
        attachStream(peer.id, remote);
      };
      pc.onicecandidate = (event) => {
        if (event.candidate) send({ type: "signal", to: peer.id, data: { candidate: event.candidate.toJSON() } });
      };
      pc.onconnectionstatechange = () => {
        if (pc.connectionState === "failed" || pc.connectionState === "closed") {
          pc.close();
          pcsRef.current.delete(peer.id);
        }
      };
      if (initiator) {
        pc.onnegotiationneeded = async () => {
          try {
            await pc.setLocalDescription(await pc.createOffer());
            send({ type: "signal", to: peer.id, data: { sdp: pc.localDescription?.toJSON() } });
          } catch {
            /* peer vanished mid-handshake */
          }
        };
      }
      return pc;
    },
    [attachStream, send],
  );

  const dropPeer = useCallback((peerId: string) => {
    pcsRef.current.get(peerId)?.close();
    pcsRef.current.delete(peerId);
    setStreams((prev) => {
      const next = { ...prev };
      delete next[peerId];
      return next;
    });
    setRaisedHands((prev) => prev.filter((id) => id !== peerId));
  }, []);

  const handleSignal = useCallback(
    async (from: string, data: { sdp?: RTCSessionDescriptionInit; candidate?: RTCIceCandidateInit }, knownPeers: PeerInfo[]) => {
      const peer = knownPeers.find((p) => p.id === from) ?? { id: from, name: from, role: "STUDENT" };
      const pc = createPeer(peer, false);
      try {
        if (data.sdp) {
          await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
          if (data.sdp.type === "offer") {
            await pc.setLocalDescription(await pc.createAnswer());
            send({ type: "signal", to: from, data: { sdp: pc.localDescription?.toJSON() } });
          }
        } else if (data.candidate) {
          await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
        }
      } catch {
        /* late candidate for a closed connection is harmless */
      }
    },
    [createPeer, send],
  );

  // ── Socket lifecycle ───────────────────────────────────────────────────────

  useEffect(() => {
    closedByUser.current = false;
    let disposed = false;

    async function startMedia(): Promise<MediaStream | null> {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        localRef.current = stream;
        setMyStream(stream);
        return stream;
      } catch {
        setMediaError("Camera/microphone unavailable — you can still follow the class, chat and see the board.");
        return null;
      }
    }

    async function connect() {
      if (disposed) return;
      // Long classes outlive the 15-minute access token; refresh first so the
      // handshake (and any reconnect after a drop) always uses a live token.
      await refreshAccessToken();
      if (disposed) return;
      const ws = new WebSocket(liveRoomUrl(classId));
      wsRef.current = ws;
      let knownPeers: PeerInfo[] = [];

      ws.onmessage = async (event) => {
        const msg = JSON.parse(event.data as string) as Record<string, never> & Record<string, unknown>;
        switch (msg.type) {
          case "welcome": {
            const myRole = (msg.you as PeerInfo).role;
            setRole(myRole);
            const sfuData = msg.sfu as { enabled?: boolean } | undefined;
            if (sfuData?.enabled) setSfuAvailable(true);
            // Capture TURN config BEFORE creating peers so the first offer
            // already contains the relay candidates.
            iceServersRef.current = ((msg.ice_servers as RTCIceServer[] | undefined) ?? []).length
              ? (msg.ice_servers as RTCIceServer[])
              : null;
            knownPeers = (msg.peers ?? []) as PeerInfo[];
            setPeers(knownPeers);
            setConnected(true);
            // In large class mode (>6 peers), students default camera off to conserve bandwidth
            if (myRole === "STUDENT" && knownPeers.length >= 6 && localRef.current) {
              localRef.current.getVideoTracks().forEach((t) => { t.enabled = false; });
              setCamOn(false);
            }
            // The newcomer offers to everyone already in the room.
            for (const peer of knownPeers) createPeer(peer, true);
            break;
          }
          case "peer-joined": {
            const peer = msg.peer as PeerInfo;
            knownPeers = [...knownPeers.filter((p) => p.id !== peer.id), peer];
            setPeers(knownPeers);
            break;
          }
          case "peer-left":
            knownPeers = knownPeers.filter((p) => p.id !== msg.peer_id);
            setPeers(knownPeers);
            dropPeer(msg.peer_id as string);
            break;
          case "chat": {
            const m = msg.message as LiveChatMessage;
            setChat((prev) => [...prev.slice(-199), m]);
            break;
          }
          case "hand":
            setRaisedHands((prev) =>
              msg.raised ? [...new Set([...prev, msg.student_id as string])] : prev.filter((id) => id !== msg.student_id),
            );
            break;
          case "signal":
            await handleSignal(msg.from as string, msg.data as { sdp?: RTCSessionDescriptionInit; candidate?: RTCIceCandidateInit }, knownPeers);
            break;
          case "whiteboard":
            if (msg.stroke === null) setStrokes([]);
            else setStrokes((prev) => [...prev.slice(-99), msg.stroke as Stroke]);
            break;
          case "screen":
            setScreenSharerId(msg.sharing ? (msg.from as string) : null);
            break;
          case "admitted":
          case "waiting-updated":
          case "roster":
            break;
          case "removed":
          case "class-ended":
            closedByUser.current = true;
            endedRef.current?.();
            ws.close();
            break;
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closedByUser.current && !disposed) {
          // Network blip — try once more after a beat.
          setTimeout(connect, 2000);
        }
      };
    }

    startMedia().finally(connect);

    const connections = pcsRef.current;
    return () => {
      disposed = true;
      closedByUser.current = true;
      wsRef.current?.close();
      connections.forEach((pc) => pc.close());
      connections.clear();
      localRef.current?.getTracks().forEach((t) => t.stop());
      localRef.current = null;
      screenTrackRef.current?.stop();
      screenTrackRef.current = null;
    };
  }, [classId, createPeer, dropPeer, handleSignal]);

  // ── Controls ───────────────────────────────────────────────────────────────

  const sendChat = useCallback((body: string) => send({ type: "chat", body }), [send]);

  const toggleHand = useCallback((raised: boolean) => send({ type: "hand", raised }), [send]);

  const toggleMic = useCallback(() => {
    const track = localRef.current?.getAudioTracks()[0];
    if (track) {
      track.enabled = !track.enabled;
      setMicOn(track.enabled);
    }
  }, []);

  const toggleCam = useCallback(() => {
    const track = localRef.current?.getVideoTracks()[0];
    if (track && track !== screenTrackRef.current) {
      track.enabled = !track.enabled;
      setCamOn(track.enabled);
    }
  }, []);

  const startScreenShare = useCallback(async () => {
    try {
      const display = await navigator.mediaDevices.getDisplayMedia({ video: true });
      const screenTrack = display.getVideoTracks()[0];
      screenTrackRef.current = screenTrack;
      pcsRef.current.forEach((pc) => {
        const sender = pc.getSenders().find((s) => s.track?.kind === "video");
        sender?.replaceTrack(screenTrack);
      });
      screenTrack.onended = () => {
        screenTrackRef.current = null;
        setScreenSharing(false);
        send({ type: "screen", sharing: false });
        const cam = localRef.current?.getVideoTracks()[0];
        pcsRef.current.forEach((pc) => {
          const sender = pc.getSenders().find((s) => s.track?.kind === "video");
          if (cam) sender?.replaceTrack(cam);
        });
      };
      setScreenSharing(true);
      send({ type: "screen", sharing: true });
    } catch {
      /* user cancelled the picker */
    }
  }, [send]);

  const stopScreenShare = useCallback(() => screenTrackRef.current?.stop(), []);

  const drawStroke = useCallback(
    (stroke: Stroke) => {
      setStrokes((prev) => [...prev.slice(-99), stroke]);
      send({ type: "whiteboard", stroke });
    },
    [send],
  );

  const clearBoard = useCallback(() => {
    setStrokes([]);
    send({ type: "whiteboard", stroke: null });
  }, [send]);

  return {
    connected,
    role,
    peers,
    streams,
    myStream,
    chat,
    raisedHands,
    screenSharerId,
    strokes,
    mediaError,
    sendChat,
    toggleHand,
    toggleMic,
    toggleCam,
    micOn,
    camOn,
    startScreenShare,
    stopScreenShare,
    screenSharing,
    drawStroke,
    clearBoard,
    isLargeClass: peers.length >= 6,
    sfuAvailable,
  };
}
