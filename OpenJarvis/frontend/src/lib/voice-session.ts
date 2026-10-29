import { create } from 'zustand';

/** A start request survives navigation from Settings to Chat, never a reload. */
export const useVoiceSession = create<{ active: boolean; startRequested: boolean }>(() => ({
  active: false,
  startRequested: false,
}));

export function requestVoiceStart() {
  useVoiceSession.setState({ startRequested: true });
}
