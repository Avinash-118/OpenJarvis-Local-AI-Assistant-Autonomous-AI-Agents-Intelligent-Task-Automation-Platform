import { describe, expect, it } from 'vitest';
import { VoiceActivity } from './voice-activity';

describe('voice turn detection', () => {
  it('does not transcribe silence or an isolated click', () => {
    const vad = new VoiceActivity();
    for (let now = 100; now < 25000; now += 100) {
      expect(vad.update(now === 300 ? 0.1 : 0.003, now)).toBe(false);
    }
    expect(vad.started).toBe(false);
  });
  it('keeps short pauses within the same turn and finishes after silence', () => {
    const vad = new VoiceActivity();
    for (let now = 100; now <= 1000; now += 100) expect(vad.update(0.06, now)).toBe(false);
    expect(vad.started).toBe(true);
    for (let now = 1100; now <= 1700; now += 100) expect(vad.update(0.003, now)).toBe(false);
    for (let now = 1800; now <= 2200; now += 100) expect(vad.update(0.06, now)).toBe(false);
    for (let now = 2300; now < 3400; now += 100) expect(vad.update(0.003, now)).toBe(false);
    expect(vad.update(0.003, 3400)).toBe(true);
  });
  it('limits a continuous utterance so it cannot record indefinitely', () => {
    const vad = new VoiceActivity();
    for (let now = 100; now < 30100; now += 100) expect(vad.update(0.08, now)).toBe(false);
    expect(vad.update(0.08, 30100)).toBe(true);
  });
});
