import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch, transcribeAudio, synthesizeSpeech } from '../lib/api';
import { toSpeakableText } from '../lib/message-text';
import { useVoiceSession } from '../lib/voice-session';
export { useVoiceSession } from '../lib/voice-session';
import { VoiceActivity } from '../lib/voice-activity';
import { useTtsStore } from '../lib/tts';

type Phase = 'off' | 'starting' | 'listening' | 'transcribing' | 'working' | 'speaking';

/** All recognition stays in local Whisper; output uses an installed OS voice. */
export function useHandsFree(onTurn: (text: string) => Promise<string>, busy: boolean) {
  const [phase, setPhase] = useState<Phase>('off');
  const [error, setError] = useState<string | null>(null);
  const [heard, setHeard] = useState('');
  const [level, setLevel] = useState(0);
  const enabled = useRef(false);
  const generation = useRef(0);
  const turn = useRef(onTurn);
  const busyRef = useRef(busy);
  turn.current = onTurn;
  busyRef.current = busy;
  const release = useRef<() => void>(() => {});
  const cancelWait = useRef<() => void>(() => {});
  const lease = useRef<string | null>(null);
  const leaseTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const browserLease = (active: boolean, token: string) => apiFetch('/v1/desktop/voice/browser', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Jarvis-Desktop': '1' },
    body: JSON.stringify({ active, token }), signal: AbortSignal.timeout(1500),
  }).catch(() => null);
  const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

  const stop = useCallback(() => {
    enabled.current = false;
    generation.current += 1;
    cancelWait.current();
    release.current();
    if (leaseTimer.current) clearInterval(leaseTimer.current);
    leaseTimer.current = null;
    if (lease.current) void browserLease(false, lease.current);
    lease.current = null;
    window.speechSynthesis?.cancel();
    useVoiceSession.setState({ active: false });
    setPhase('off');
    setLevel(0);
  }, []);

  useEffect(() => stop, [stop]);

  const start = useCallback(async () => {
    if (enabled.current) return;
    setError(null);
    setHeard('');
    setPhase('starting');
    enabled.current = true;
    useVoiceSession.setState({ active: true });
    useTtsStore.getState().stop();
    const mine = ++generation.current;
    const live = () => enabled.current && generation.current === mine;
    let stream: MediaStream | null = null;
    let context: AudioContext | null = null;
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
        throw new Error('Use Chrome or Edge on localhost for microphone access.');
      }
      const token = crypto.randomUUID();
      lease.current = token;
      await browserLease(true, token);
      if (!live()) return;
      leaseTimer.current = setInterval(() => { void browserLease(true, token); }, 5000);
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      if (!live()) { stream.getTracks().forEach((track) => track.stop()); return; }
      context = new AudioContext();
      await context.resume();
      const analyser = context.createAnalyser();
      analyser.fftSize = 2048;
      const source = context.createMediaStreamSource(stream);
      source.connect(analyser); // Never connect the microphone to the speakers.
      const samples = new Float32Array(analyser.fftSize);
      const audioStream = stream;
      release.current = () => {
        audioStream.getTracks().forEach((track) => track.stop());
        if (context && context.state !== 'closed') void context.close();
      };

      const record = () => new Promise<Blob | null>((resolve, reject) => {
        const chunks: Blob[] = [];
        const recorder = new MediaRecorder(audioStream);
        const detector = new VoiceActivity();
        const began = performance.now();
        let ended = false;
        let discard = false;
        const finish = (skip = false) => {
          if (ended) return;
          ended = true;
          discard = skip;
          clearInterval(ticker);
          if (recorder.state !== 'inactive') recorder.stop();
        };
        const ticker = setInterval(() => {
          if (!live() || busyRef.current) { finish(true); return; }
          analyser.getFloatTimeDomainData(samples);
          let energy = 0;
          for (const sample of samples) energy += sample * sample;
          const rms = Math.sqrt(energy / samples.length);
          setLevel(Math.min(1, rms * 12));
          const now = performance.now();
          if (detector.update(rms, now)) finish();
          else if (!detector.started && now - began > 20000) finish(true);
        }, 80);
        recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
        recorder.onstop = () => {
          clearInterval(ticker);
          resolve(discard || !live() ? null : new Blob(chunks, { type: recorder.mimeType }));
        };
        recorder.onerror = () => {
          clearInterval(ticker);
          reject(new Error('Microphone recording failed. Check your input device.'));
        };
        cancelWait.current = () => finish(true);
        recorder.start(250);
      });

      const speak = async (text: string) => {
        const spoken = toSpeakableText(text).slice(0, 2500);
        if (!spoken || !live()) return;
        const controller = new AbortController();
        cancelWait.current = () => controller.abort();
        const blob = await synthesizeSpeech(spoken, { signal: controller.signal });
        if (!live()) return;
        setPhase('speaking');
        const url = URL.createObjectURL(blob);
        const player = new Audio(url);
        await new Promise<void>((resolve, reject) => {
          let finished = false;
          const timeout = setTimeout(() => done(new Error('Speech playback timed out.')), 240000);
          const done = (err?: Error) => {
            if (finished) return;
            finished = true;
            clearTimeout(timeout);
            player.onended = null; player.onerror = null;
            player.pause(); player.src = '';
            URL.revokeObjectURL(url);
            if (err) reject(err); else resolve();
          };
          cancelWait.current = () => done();
          player.onended = () => done();
          player.onerror = () => done(new Error('Speech playback failed. Check your output device.'));
          void player.play().catch((err) => done(new Error(`Allow audio playback in this browser: ${err.message}`)));
        });
      };

      while (live()) {
        if (busyRef.current) { setPhase('working'); await sleep(150); continue; }
        setPhase('listening');
        const blob = await record();
        if (!blob || !live()) continue;
        setLevel(0);
        setPhase('transcribing');
        const result = await transcribeAudio(blob);
        if (!live()) break;
        const text = result.text.trim().replace(/^(?:hey\s+)?(?:jarvis|openjarvis)[,!.:\s]+/i, '').trim();
        if (!text || /^(?:thank you[.!]?|thanks for watching[.!]?|you[.!]?)$/i.test(text)) continue;
        setHeard(text);
        if (/^(?:please\s+)?(?:stop listening|turn off voice(?: mode)?|stop voice(?: mode)?|go to sleep)[.!]?$/i.test(text)) {
          stop(); break;
        }
        setPhase('working');
        const reply = await turn.current(text);
        if (!live()) break;
        await speak(reply);
        // Let speaker echo fade before starting the next recording.
        await sleep(450);
      }
    } catch (err) {
      if (live()) setError(err instanceof Error ? err.message : 'Voice mode failed.');
    } finally {
      stream?.getTracks().forEach((track) => track.stop());
      if (context && context.state !== 'closed') void context.close();
      // A stale getUserMedia/Whisper response must not switch off a newer session.
      if (generation.current === mine) stop();
    }
  }, [stop]);

  return { phase, error, heard, level, active: phase !== 'off', start, stop };
}
