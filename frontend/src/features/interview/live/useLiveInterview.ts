import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import type { LiveHandoff } from "../api";
import { openCapture, type Capture } from "../audio/capture";
import { QuestionPlayer } from "../audio/player";
import { initialLiveState, liveReducer, type LiveState } from "./liveReducer";
import { MAX_ANSWER_SECONDS, parseServerMessage, voiceSocketUrl, type ClientMessage } from "./protocol";

/** If the server hasn't confirmed an end request by then, close the socket ourselves. */
const END_TIMEOUT_MS = 20_000;

export interface LiveInterview {
  state: LiveState;
  /** The mic could not be opened, so answers are typed. */
  typing: boolean;
  setTyping: (typing: boolean) => void;
  micProblem: string | null;
  /** The browser blocked autoplay: the question waits for a tap. */
  audioBlocked: boolean;
  unblockAudio: () => void;
  replay: () => void;
  skipAudio: () => void;
  level: () => number;
  recordingSeconds: number;
  startRecording: () => void;
  stopRecording: () => void;
  sendText: (text: string) => void;
  end: () => void;
}

export function useLiveInterview(handoff: LiveHandoff): LiveInterview {
  const [state, dispatch] = useReducer(liveReducer, initialLiveState);
  const [typing, setTyping] = useState(handoff.mode === "text");
  const [micProblem, setMicProblem] = useState<string | null>(null);
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);

  const socket = useRef<WebSocket | null>(null);
  const player = useRef<QuestionPlayer | null>(null);
  const capture = useRef<Capture | null>(null);
  // Handlers run outside render (socket events, timers), so they read the
  // phase through a ref kept in step with state.
  const phase = useRef(state.phase);
  useEffect(() => {
    phase.current = state.phase;
  }, [state.phase]);

  const send = useCallback((message: ClientMessage) => {
    const ws = socket.current;
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(message));
  }, []);

  /** After the question's audio has arrived: wait for playback, then it's the user's turn. */
  const awaitPlayback = useCallback(async () => {
    const p = player.current;
    if (!p) return;
    if (p.blocked) {
      setAudioBlocked(true);
      return;
    }
    await p.drained();
    dispatch({ type: "question_heard" });
  }, []);

  useEffect(() => {
    const ws = new WebSocket(voiceSocketUrl());
    ws.binaryType = "arraybuffer";
    socket.current = ws;
    const questionPlayer = new QuestionPlayer();
    player.current = questionPlayer;
    let closed = false;

    // Sent only once this socket is open: under StrictMode a first,
    // discarded socket is closed before it opens and never spends the token.
    ws.onopen = () => ws.send(JSON.stringify({ type: "session.start", token: handoff.token }));
    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        questionPlayer.feed(event.data);
        return;
      }
      const message = parseServerMessage(event.data);
      if (!message) return;
      if (message.type === "question.text") questionPlayer.reset();
      if (message.type === "error" && message.code === "answer_too_long" && phase.current === "recording") {
        // The server drops audio until audio.end; close this answer so it starts afresh.
        capture.current?.pause();
        ws.send(JSON.stringify({ type: "audio.end" }));
      }
      dispatch({ type: "server", message });
      if (message.type === "question.audio_end") void awaitPlayback();
    };
    ws.onclose = (event) => {
      closed = true;
      dispatch({ type: "closed", code: event.code });
    };

    if (handoff.mode === "voice") {
      openCapture(handoff.deviceId).then(
        (opened) => {
          if (socket.current !== ws) opened.close();
          else capture.current = opened;
        },
        () => {
          setTyping(true);
          setMicProblem("We couldn't open your microphone, so you can type your answers instead.");
        },
      );
    }

    return () => {
      // Closing an open socket mid-interview makes it `interrupted`, with a
      // partial report (decision 041).
      if (!closed) ws.close(1000);
      socket.current = null;
      questionPlayer.close();
      player.current = null;
      capture.current?.close();
      capture.current = null;
    };
  }, [handoff, awaitPlayback]);

  const stopRecording = useCallback(() => {
    if (phase.current !== "recording") return;
    capture.current?.pause(); // flushes the last chunk before audio.end
    send({ type: "audio.end" });
    dispatch({ type: "answer_sent" });
  }, [send]);

  const startRecording = useCallback(() => {
    const mic = capture.current;
    const ws = socket.current;
    if (!mic || !ws || phase.current !== "answering") return;
    player.current?.stop();
    mic.record((pcm) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(pcm);
    });
    setRecordingSeconds(0);
    dispatch({ type: "record_started" });
  }, []);

  // The answer timer, and the automatic stop just before the server's limit.
  useEffect(() => {
    if (state.phase !== "recording") return;
    const started = Date.now();
    const id = window.setInterval(() => {
      const seconds = Math.floor((Date.now() - started) / 1000);
      setRecordingSeconds(seconds);
      if (seconds >= MAX_ANSWER_SECONDS) stopRecording();
    }, 250);
    return () => window.clearInterval(id);
  }, [state.phase, stopRecording]);

  // An end request the server never confirms (it only reads messages
  // between turns) still ends, by closing the socket.
  useEffect(() => {
    if (state.phase !== "ending") return;
    const id = window.setTimeout(() => socket.current?.close(1000), END_TIMEOUT_MS);
    return () => window.clearTimeout(id);
  }, [state.phase]);

  const sendText = useCallback(
    (text: string) => {
      if (phase.current !== "answering" || !text.trim()) return;
      player.current?.stop();
      send({ type: "answer.text", text: text.trim() });
      dispatch({ type: "answer_sent" });
    },
    [send],
  );

  const end = useCallback(() => {
    if (phase.current === "recording") capture.current?.pause();
    player.current?.stop();
    send({ type: "session.end" });
    dispatch({ type: "end_requested" });
  }, [send]);

  const unblockAudio = useCallback(() => {
    const p = player.current;
    if (!p) return;
    setAudioBlocked(false);
    void p.replay().then(() => dispatch({ type: "question_heard" }));
  }, []);

  const replay = useCallback(() => {
    if (phase.current !== "answering" && phase.current !== "asking") return;
    void player.current?.replay();
  }, []);

  /** Stop the question playing and answer now. Only once all its audio has
   * arrived: the server reads answers after it has finished sending. */
  const skipAudio = useCallback(() => {
    player.current?.stop();
    dispatch({ type: "question_heard" });
  }, []);

  const level = useCallback(() => capture.current?.level() ?? 0, []);

  return {
    state,
    typing,
    setTyping,
    micProblem,
    audioBlocked,
    unblockAudio,
    replay,
    skipAudio,
    level,
    recordingSeconds,
    startRecording,
    stopRecording,
    sendText,
    end,
  };
}
