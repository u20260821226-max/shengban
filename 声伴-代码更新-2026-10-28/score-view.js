// Engrave the actual MusicXML; transpose both the score and playback together.
export class ScoreView {
  constructor(container) {
    this.display = new opensheetmusicdisplay.OpenSheetMusicDisplay(container, {
      autoResize: true, backend: 'svg', drawTitle: false, drawSubtitle: false,
      drawComposer: false, drawLyricist: false, drawPartNames: true,
      drawingParameters: 'compacttight',
    });
    this.display.TransposeCalculator = new opensheetmusicdisplay.TransposeCalculator();
  }
  async load(url) {
    await this.display.load(url);
    this.display.Zoom = .65;
    this.display.render();
  }
  transpose(semitone) {
    if (!this.display.Sheet) return;
    this.display.Sheet.Transpose = semitone;
    this.display.updateGraphic();
    this.display.render();
  }
}
