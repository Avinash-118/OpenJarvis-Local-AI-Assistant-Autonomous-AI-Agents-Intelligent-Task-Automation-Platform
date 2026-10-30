import { useEffect, useState } from 'react';
import { apiFetch } from '../lib/api';

type VoiceStatus = {
  running: boolean; phase: string; paused: boolean; autostart: boolean; error?: string | null;
};

export function BackgroundVoiceStatus() {
  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [error, setError] = useState('');
  const disconnected = () => setStatus((previous) => previous ? { ...previous, running: false, phase: 'reconnecting', error: null } : null);
  const refresh = async () => {
    try {
      const response = await apiFetch('/v1/desktop/voice', { headers: { 'X-Jarvis-Desktop': '1' }, signal: AbortSignal.timeout(2500) });
      if (response.ok) setStatus(await response.json());
      else disconnected();
    } catch { disconnected(); }
  };
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => { void refresh(); }, 5000);
    return () => clearInterval(timer);
  }, []);
  if (!status || (!status.autostart && !status.running)) return null;
  const labels: Record<string, string> = {
    'wake-word': 'Ready — say Jarvis', listening: 'Listening', working: 'Thinking',
    transcribing: 'Understanding speech', speaking: 'Speaking', locked: 'Windows is locked',
    'browser-voice': 'Using browser voice', starting: 'Starting', error: 'Needs attention', stopped: 'Stopped',
    reconnecting: 'Reconnecting to Jarvis…', paused: 'Resuming…',
  };
  const label = status.paused ? 'Microphone paused' : labels[status.phase] ?? status.phase;
  const toggle = async () => {
    setError('');
    try {
      const response = await apiFetch('/v1/desktop/voice/pause', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Jarvis-Desktop': '1' },
        body: JSON.stringify({ paused: !status.paused }),
      });
      if (!response.ok) throw new Error('Could not change the background microphone.');
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : 'Voice control failed.'); }
  };
  return (
    <div className="py-3 space-y-2" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm">Wake word: Jarvis</div>
          <div className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>
            {status.autostart ? 'Starts when you sign in to Windows. ' : ''}
            Works with the browser closed. Say Jarvis, then your request.
          </div>
        </div>
        <button type="button" onClick={() => void toggle()} disabled={!status.running}
          className="px-3 py-2 rounded-lg text-xs whitespace-nowrap cursor-pointer disabled:opacity-40"
          style={{ border: '1px solid var(--color-border)' }}>
          {status.paused ? 'Resume microphone' : 'Pause microphone'}
        </button>
      </div>
      <p role="status" className="text-xs" style={{ color: status.running && !status.paused && !status.error ? 'var(--color-success)' : 'var(--color-text-secondary)' }}>{label}</p>
      {(error || status.error) && <p role="alert" className="text-xs" style={{ color: 'var(--color-error)' }}>{error || status.error}</p>}
    </div>
  );
}
