import { describe, expect, it } from 'vitest';
import { wakeCommand } from './wake-command';

describe('strict voice activation', () => {
  it('requires Hello Jarvis on every request, including immediately after a reply', () => {
    expect(wakeCommand('Hello Jarvis, open WhatsApp')).toBe('open WhatsApp');
    expect(wakeCommand('send hi to Mummy')).toBeNull();
    expect(wakeCommand('Hello Jarvis, send hi to Mummy')).toBe('send hi to Mummy');
    expect(wakeCommand('confirm send')).toBeNull();
  });

  it('allows punctuation and case without accepting names or mentions', () => {
    expect(wakeCommand('  HELLO, Jarvis!  ')).toBe('');
    for (const text of [
      '', 'Jarvis', 'Hi Jarvis', 'hey Jarvis open gmail', 'HelloJarvis',
      'Hello Jarvison', 'hello service', 'she said hello jarvis', 'open WhatsApp',
    ]) expect(wakeCommand(text)).toBeNull();
  });
});
