// All tracks use the same local acoustic piano samples. MIDI times stay in source seconds.
export class MusicPlayer {
  constructor(onState) {
    this.onState = onState;
    this.position = 0;
    this.rate = 1;
    this.semitone = 0;
    this.mode = 'accompaniment';
    this.playing = false;
    this.voices = new Set();
    this.buffers = new Map();
    this.samples = [{ midi: 21, name: 'A0' }];
    for (let octave = 1; octave <= 7; octave++) {
      ['C', 'Ds', 'Fs', 'A'].forEach((name, i) => this.samples.push({ midi: 12 * (octave + 1) + i * 3, name: name + octave }));
    }
    this.samples.push({ midi: 108, name: 'C8' });
  }
  async load(song) {
    this.pause();
    this.song = song;
    this.position = 0;
    this.rate = 1;
    this.semitone = 0;
    this.loop = null;
    this.emit();
  }
  sampleFor(midi) {
    return this.samples.reduce((best, sample) => Math.abs(sample.midi - midi) < Math.abs(best.midi - midi) ? sample : best);
  }
  async prepare() {
    this.context ||= new AudioContext();
    if (!this.output) {
      this.output = this.context.createDynamicsCompressor();
      this.output.threshold.value = -12;
      this.output.ratio.value = 5;
      this.output.connect(this.context.destination);
    }
    await this.context.resume();
    const needed = new Set(this.song.notes.map(note => this.sampleFor(note.midi + this.semitone).name));
    await Promise.all([...needed].map(async name => {
      if (this.buffers.has(name)) return;
      const response = await fetch(`assets/piano/${name}.mp3`);
      if (!response.ok) throw new Error('钢琴音色加载失败，请刷新重试');
      this.buffers.set(name, await this.context.decodeAudioData(await response.arrayBuffer()));
    }));
  }
  async play(countIn = false) {
    if (this.playing || !this.song) return;
    const generation = this.generation = (this.generation || 0) + 1;
    await this.prepare();
    if (generation !== this.generation) return;
    if (this.position >= this.song.duration) this.position = 0;
    const delay = countIn ? 4 * 60 / (this.song.bpm * this.rate) : 0;
    this.anchorPosition = this.position;
    this.anchorTime = this.context.currentTime + delay;
    if (countIn) this.countIn(delay);
    this.nextNote = this.song.notes.findIndex(note => note.time + note.duration > this.position + .001);
    if (this.nextNote < 0) this.nextNote = this.song.notes.length;
    this.playing = true;
    this.timer = setInterval(() => this.tick(), 25);
    this.tick();
  }
  currentPosition() {
    return this.playing ? Math.min(this.song.duration, this.anchorPosition + Math.max(0, this.context.currentTime - this.anchorTime) * this.rate) : this.position;
  }
  tick() {
    this.position = this.currentPosition();
    const end = this.loop?.end ?? this.song.duration;
    if (this.position >= end) {
      if (this.loop) this.seek(this.loop.start);
      else { this.pause(); this.position = this.song.duration; this.emit(); }
      return;
    }
    const horizon = Math.min(end, this.position + .12 * this.rate);
    while (this.nextNote < this.song.notes.length && this.song.notes[this.nextNote].time < horizon) {
      const note = this.song.notes[this.nextNote++];
      if (this.mode === 'accompaniment' && note.role === 'melody') continue;
      const offset = Math.max(0, this.anchorPosition - note.time);
      const time = Math.max(this.context.currentTime + .005, this.anchorTime + (note.time - this.anchorPosition) / this.rate);
      this.sound(note, time, (Math.min(note.time + note.duration, end) - note.time - offset) / this.rate);
    }
    this.emit();
  }
  sound(note, time, duration) {
    if (duration <= 0) return;
    const sample = this.sampleFor(note.midi + this.semitone);
    const buffer = this.buffers.get(sample.name);
    if (!buffer) return;
    const source = this.context.createBufferSource();
    const gain = this.context.createGain();
    source.buffer = buffer;
    source.playbackRate.value = 2 ** ((note.midi + this.semitone - sample.midi) / 12);
    const level = Math.min(.65, .18 + note.velocity * .38) * (note.role === 'melody' ? 1.05 : .8);
    gain.gain.setValueAtTime(level, time);
    gain.gain.setValueAtTime(level, time + duration);
    gain.gain.exponentialRampToValueAtTime(.0001, time + duration + .18);
    source.connect(gain).connect(this.output);
    source.start(time);
    source.stop(time + duration + .2);
    this.voices.add(source);
    source.onended = () => { source.disconnect(); gain.disconnect(); this.voices.delete(source); };
  }
  countIn(delay) {
    for (let i = 0; i < 4; i++) {
      const source = this.context.createOscillator(), gain = this.context.createGain();
      const time = this.context.currentTime + i * delay / 4;
      source.frequency.value = i === 0 ? 1000 : 750;
      gain.gain.setValueAtTime(.1, time);
      gain.gain.exponentialRampToValueAtTime(.0001, time + .07);
      source.connect(gain).connect(this.context.destination);
      source.start(time); source.stop(time + .08);
      this.voices.add(source);
      source.onended = () => { source.disconnect(); gain.disconnect(); this.voices.delete(source); };
    }
  }
  pause() {
    this.generation = (this.generation || 0) + 1;
    this.position = this.currentPosition();
    this.playing = false;
    clearInterval(this.timer);
    for (const voice of this.voices) { try { voice.stop(); } catch {} }
    this.voices.clear();
    this.emit();
  }
  async seek(position) {
    const resume = this.playing;
    this.pause();
    this.position = Math.max(0, Math.min(this.song.duration, position));
    this.emit();
    if (resume) await this.play();
  }
  async configure(values) {
    const resume = this.playing;
    this.pause();
    Object.assign(this, values);
    this.emit();
    if (resume) await this.play();
  }
  emit() { this.onState?.(this); }
}
