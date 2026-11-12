/** null means ambient speech; an empty string means just the wake greeting. */
export function wakeCommand(transcript: string): string | null {
  const text = transcript.trim();
  const wake = /^hello[,\s]+jarvis\b[,.:!?\s]*/i.exec(text);
  return wake ? text.slice(wake[0].length).trim() : null;
}

export const WAKE_REPLY = 'Hello. Say Hello Jarvis followed by your request.';
