/** Silence-based turn detection, independent of browser APIs for testing. */
export class VoiceActivity {
  private firstSound = 0;
  private lastSound = 0;
  private voicedMs = 0;
  private previousTime = 0;
  private noise = 0.004;
  started = false;

  update(rms: number, now: number): boolean {
    const elapsed = this.previousTime ? Math.min(now - this.previousTime, 200) : 0;
    this.previousTime = now;
    const threshold = Math.max(0.012, Math.min(this.noise * 3, 0.045));
    if (rms > threshold) {
      if (!this.firstSound) this.firstSound = now;
      this.lastSound = now;
      this.voicedMs += elapsed;
      if (this.voicedMs >= 250) this.started = true;
    } else if (!this.started) {
      this.noise = this.noise * 0.95 + Math.min(rms, 0.015) * 0.05;
      // A single bump or keyboard tap should not become a spoken command.
      if (now - this.lastSound > 350) {
        this.firstSound = 0;
        this.voicedMs = 0;
      }
    }
    return this.started && (now - this.lastSound >= 1200 || now - this.firstSound >= 30000);
  }
}
