import { apiFetch } from './api';

export interface DesktopReply { handled: boolean; response?: string; actions?: string[] }

export async function runDesktopCommand(
  text: string,
  messages: Array<{ role: string; content: string }>,
  signal: AbortSignal,
): Promise<DesktopReply> {
  const id = crypto.randomUUID();
  const cancel = () => {
    void apiFetch('/v1/desktop/cancel', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Jarvis-Desktop': '1' },
      body: JSON.stringify({ id }),
    }).catch(() => {});
  };
  signal.addEventListener('abort', cancel, { once: true });
  try {
    const res = await apiFetch('/v1/desktop/command', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Jarvis-Desktop': '1' },
      body: JSON.stringify({ id, text, messages: messages.slice(-12) }), signal,
    });
    // Older/unmodified OpenJarvis backends continue to support ordinary chat.
    if (res.status === 404) return { handled: false };
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Desktop command failed (${res.status})`);
    }
    return res.json();
  } finally {
    signal.removeEventListener('abort', cancel);
  }
}
