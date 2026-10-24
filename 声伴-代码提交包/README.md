# 声伴 · 比赛演示

静态网页已接入《爱永在》《小幸运》和《有一种悲伤》。使用项目方提供的 MIDI、MuseScore / MusicXML 乐谱和两种 MP3；原文件保持不变，运行资源放在 assets/。

## 运行

在项目目录运行 `python3 -m http.server 4173`，浏览器打开 http://localhost:4173 。也可双击“启动声伴.command”。保持终端窗口打开。

## 已接入

- 默认曲目《爱永在》替换旧 C 大调示范，曲库增加《小幸运》。
- 两个模式：纯伴奏只播放 Piano；旋律提示播放 Voice + Piano，所有声部统一使用钢琴采样。
- 播放、暂停、从头播放、进度跳转、前后小节、60–160 BPM 调速、±6 半音移调；移调同时更新谱面。
- A/B 起止点循环、播放前 4 拍倒数。
- 真实 MusicXML 谱面可滚动阅读；当前位置按小节显示，不假冒逐音跟随游标。
- 两种 MP3 备用录音保持原调原速，不随 MIDI 控件改变。
- 所有播放资源本地打包，首次联网打开并完成缓存后可断网使用。文件新增后要更新 asset-list.json。

## 代码边界

practice-app.js 管理页面；music-player.js 调度 MIDI 音符与钢琴采样；score-view.js 使用本地 OSMD 渲染 MusicXML；assets/scores/*.json 为 MIDI 预处理数据。旧原型文件已移至 archive/prototype/，当前网页未引用。

MIDI 保留源文件中的速度变化，速度滑杆按比例缩放；不自动修复识谱错误。后台自动识谱、账户和上传仍未接通，导入入口明确说明需要预先校对。

运行与演示说明见 DEMO_GUIDE.md。资源授权见 assets/ATTRIBUTION.md。

## 整理与提交

双击 scripts/整理代码.command，生成 dist/ 下的网页发布包、代码提交包和资源校验清单。原始乐谱保持原位置。工程结构见 [代码说明](docs/代码说明.md)，交付方式见 [提交与验证](docs/提交与验证.md)。
