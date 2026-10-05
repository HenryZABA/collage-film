#!/usr/bin/env node
/** Build an offline, seekable HyperFrames collage from a portable JSON job. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const RATIOS = { '9:16': [1080, 1920], '4:5': [1080, 1350], '3:4': [1080, 1440], '1:1': [1080, 1080], '16:9': [1920, 1080] };
const GRADES = {
  none: null,
  'warm-film': { preset: 'vintage-wash', intensity: 0.6, details: { vignette: 0.12, grain: 0.12, grainSize: 0.2, grainRoughness: 0.6 } },
  'cool-editorial': { intensity: 0.65, adjust: { contrast: 0.08, highlights: -0.08, shadows: 0.04, temperature: -0.08, saturation: -0.06 } },
};
const PLATFORMS = ['instagram', 'tiktok', 'xiaohongshu', 'youtube', 'custom'];
const MOTIONS = ['rise', 'slide-left', 'slide-right', 'float', 'none'];
const fail = message => { throw new Error(message); };
const number = (v, d, min, max, key) => { const n = v === undefined ? d : v; if (typeof n !== 'number' || !Number.isFinite(n) || n < min || n > max) fail(`${key} must be a number in ${min}..${max}`); return n; };
const text = (v, d, max, key) => { const s = v === undefined ? d : v; if (typeof s !== 'string' || s.length > max) fail(`${key} must be text, at most ${max} characters`); return s; };
const choice = (v, d, values, key) => { const x = v ?? d; if (!values.includes(x)) fail(`${key} must be one of: ${values.join(', ')}`); return x; };
const obj = (v, key) => { if (!v || typeof v !== 'object' || Array.isArray(v)) fail(`${key} must be an object`); return v; };
const keys = (v, allowed, key) => { obj(v, key); for (const k of Object.keys(v)) if (!allowed.includes(k)) fail(`Unknown ${key}.${k}`); };
const hex = (v, d, key) => { const s = v ?? d; if (!/^#[0-9a-f]{6}$/i.test(s)) fail(`${key} must be a six-digit hex color`); return s; };
const html = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const scriptJSON = v => JSON.stringify(v).replace(/[<>&\u2028\u2029]/g, c => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);
const round = n => Math.round(n * 1000000) / 1000000;

function run(bin, args, options = {}) {
  try { return execFileSync(bin, args, { encoding: 'utf8', maxBuffer: 8 * 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'], ...options }); }
  catch (e) { fail(`${bin} failed: ${String(e.stderr || e.message).slice(0, 2000)}`); }
}
function probe(file) {
  const value = JSON.parse(run('ffprobe', ['-v', 'error', '-show_streams', '-show_format', '-of', 'json', file]));
  return value;
}
function parseArgs() {
  const result = {};
  for (let i = 2; i < process.argv.length; i++) {
    const arg = process.argv[i];
    if (arg === '--help' || arg === '-h') {
      console.log('Usage: node build.mjs --config job.json --out project [--overwrite] [--gsap gsap.min.js] [--hf-bin hyperframes.mjs]\nThe output contains index.html, copied media, local GSAP and job.resolved.json. No video is rendered.');
      process.exit(0);
    }
    if (arg === '--overwrite') { result.overwrite = true; continue; }
    if (!['--config', '--out', '--gsap', '--hf-bin'].includes(arg) || !process.argv[i + 1] || process.argv[i + 1].startsWith('--')) fail(`Invalid argument: ${arg}`);
    result[arg.slice(2)] = process.argv[++i];
  }
  if (!result.config || !result.out) fail('--config and --out are required');
  return result;
}

function main() {
  const args = parseArgs();
  const configFile = path.resolve(args.config);
  const base = path.dirname(configFile);
  const output = path.resolve(args.out);
  const input = JSON.parse(fs.readFileSync(configFile, 'utf8'));
  keys(input, ['schemaVersion', 'title', 'style', 'platform', 'ratio', 'fps', 'grade', 'palette', 'bgm', 'font', 'overlay', 'endCard', 'scenes'], 'job');
  if (input.schemaVersion !== 1) fail('schemaVersion must be 1');
  if (!input.platform || !input.ratio) fail('platform and ratio are required; collect these choices from the user before building');
  const platform = choice(input.platform, null, PLATFORMS, 'platform');
  const ratio = choice(input.ratio, null, Object.keys(RATIOS), 'ratio');
  const [width, height] = RATIOS[ratio];
  const fps = choice(input.fps, 30, [24, 25, 30, 50, 60], 'fps');
  const title = text(input.title, 'Collage Film', 160, 'title');
  const style = choice(input.style, 'cutout-reveal', ['cutout-reveal', 'editorial'], 'style');
  const grade = choice(input.grade, 'none', Object.keys(GRADES), 'grade');
  const paletteInput = input.palette ?? {};
  keys(paletteInput, ['background', 'ink', 'accent'], 'palette');
  const palette = { background: hex(paletteInput.background, '#f4eadb', 'palette.background'), ink: hex(paletteInput.ink, '#191916', 'palette.ink'), accent: hex(paletteInput.accent, '#de5a38', 'palette.accent') };
  if (!Array.isArray(input.scenes) || input.scenes.length < 1 || input.scenes.length > 60) fail('scenes must contain 1..60 scenes');
  if (fs.existsSync(path.join(output, 'index.html')) && !args.overwrite) fail('Output already has index.html; use a fresh directory or --overwrite');
  if (output === base || output === path.dirname(HERE)) fail('Output must be a dedicated project subdirectory, not the config/skill directory');
  const assetCache = new Map();
  const filesToCopy = new Map();
  function localFile(value, key) {
    if (typeof value !== 'string' || !value || /^[a-z]+:\/\//i.test(value) || value.includes('\0')) fail(`${key} must be a local file path`);
    const absolute = path.resolve(base, value);
    if (!fs.existsSync(absolute) || !fs.statSync(absolute).isFile()) fail(`${key} does not exist: ${absolute}`);
    return absolute;
  }
  function asset(value, key, kind) {
    const absolute = localFile(value, key);
    const cacheKey = `${kind}:${absolute}`;
    if (assetCache.has(cacheKey)) return assetCache.get(cacheKey);
    const extension = path.extname(absolute).toLowerCase();
    if (kind === 'cutout' && extension !== '.png') fail(`${key} must be a transparent PNG`);
    if (kind === 'background' && !['.png', '.jpg', '.jpeg', '.webp'].includes(extension)) fail(`${key} must be PNG, JPEG or WebP`);
    const metadata = probe(absolute);
    const stream = metadata.streams.find(s => s.codec_type === (kind === 'audio' ? 'audio' : 'video'));
    if (!stream) fail(`${key} has no ${kind === 'audio' ? 'audio' : 'image'} stream`);
    if (kind !== 'audio' && (!(stream.width > 0) || !(stream.height > 0) || stream.width * stream.height > 32_000_000)) fail(`${key} has invalid dimensions or exceeds 32 megapixels`);
    let transparentPixels;
    if (kind === 'cutout') {
      const rgba = run('ffmpeg', ['-v', 'error', '-i', absolute, '-frames:v', '1', '-pix_fmt', 'rgba', '-f', 'rawvideo', '-'], { encoding: null, maxBuffer: stream.width * stream.height * 4 + 1024 });
      let visible = 0; transparentPixels = 0;
      for (let i = 3; i < rgba.length; i += 4) { if (rgba[i] < 255) transparentPixels++; if (rgba[i] > 0) visible++; }
      if (transparentPixels === 0 || visible === 0) fail(`${key} needs actual transparent AND visible pixels; an opaque or empty PNG is not a cutout`);
    }
    const hash = crypto.createHash('sha256').update(fs.readFileSync(absolute)).digest('hex');
    const relative = `assets/${hash.slice(0, 16)}${extension}`;
    filesToCopy.set(relative, absolute);
    const result = { path: relative, width: stream.width, height: stream.height, sha256: hash, ...(transparentPixels === undefined ? {} : { transparentPixels }) };
    assetCache.set(cacheKey, result);
    return result;
  }
  let duration = 0;
  const scenes = input.scenes.map((s, index) => {
    const name = `scenes[${index}]`;
    if (style === 'cutout-reveal') {
      keys(s, ['duration', 'photo', 'cutout', 'leadIn', 'position', 'fit', 'title', 'subtitle'], name);
      const sceneDuration = number(s.duration, 0.65, 0.4, 30, `${name}.duration`);
      const photo = asset(s.photo, `${name}.photo`, 'background');
      const cutout = s.cutout ? asset(s.cutout, `${name}.cutout`, 'cutout') : null;
      if (cutout && (photo.width !== cutout.width || photo.height !== cutout.height)) fail(`${name}: photo and cutout must have exactly the same full-canvas pixel dimensions; do not trim transparent margins`);
      const position = s.position ?? {};
      keys(position, ['x', 'y'], `${name}.position`);
      const leadIn = index === 0 ? 0 : number(s.leadIn, 0.25, 0, Math.min(1, input.scenes[index - 1].duration ?? 0.65), `${name}.leadIn`);
      const scene = { id: `scene-${index}`, start: round(duration), duration: sceneDuration, photo, cutout, leadIn, fit: choice(s.fit, 'cover', ['cover', 'contain'], `${name}.fit`), position: { x: number(position.x, 0.5, 0, 1, `${name}.position.x`), y: number(position.y, 0.5, 0, 1, `${name}.position.y`) }, title: text(s.title, '', 100, `${name}.title`), subtitle: text(s.subtitle, '', 180, `${name}.subtitle`) };
      duration = round(duration + sceneDuration);
      return scene;
    }
    keys(s, ['duration', 'title', 'subtitle', 'background', 'layers'], name);
    const sceneDuration = number(s.duration, 4, 1.5, 30, `${name}.duration`);
    if (!Array.isArray(s.layers) || s.layers.length < 1 || s.layers.length > 12) fail(`${name}.layers must contain 1..12 cutout layers`);
    const scene = { id: `scene-${index}`, start: round(duration), duration: sceneDuration, title: text(s.title, '', 100, `${name}.title`), subtitle: text(s.subtitle, '', 180, `${name}.subtitle`), background: s.background ? asset(s.background, `${name}.background`, 'background') : null, layers: s.layers.map((l, j) => {
      const layerKey = `${name}.layers[${j}]`;
      keys(l, ['path', 'x', 'y', 'width', 'rotation', 'motion'], layerKey);
      return { ...asset(l.path, `${layerKey}.path`, 'cutout'), x: number(l.x, 0.5, -0.5, 1.5, `${layerKey}.x`), y: number(l.y, 0.57, -0.5, 1.5, `${layerKey}.y`), widthFraction: number(l.width, 0.62, 0.05, 2, `${layerKey}.width`), rotation: number(l.rotation, 0, -180, 180, `${layerKey}.rotation`), motion: choice(l.motion, 'rise', MOTIONS, `${layerKey}.motion`) };
    }) };
    duration = round(duration + sceneDuration);
    return scene;
  });
  const pictureDuration = duration;
  let overlay = null;
  if (input.overlay) {
    keys(input.overlay, ['text', 'color'], 'overlay');
    overlay = { text: text(input.overlay.text, '', 160, 'overlay.text'), color: hex(input.overlay.color, '#ffffff', 'overlay.color') };
  }
  let endCard = null;
  if (input.endCard) {
    keys(input.endCard, ['duration', 'title', 'subtitle'], 'endCard');
    endCard = { duration: number(input.endCard.duration, 2, 0.5, 15, 'endCard.duration'), title: text(input.endCard.title, '', 120, 'endCard.title'), subtitle: text(input.endCard.subtitle, '', 180, 'endCard.subtitle') };
    duration = round(duration + endCard.duration);
  }
  if (duration > 300) fail('Total duration exceeds 300 seconds');
  let bgm = null;
  if (input.bgm !== undefined && input.bgm !== null) {
    keys(input.bgm, ['path', 'volume', 'fadeIn', 'fadeOut', 'offset', 'loop'], 'bgm');
    const source = localFile(input.bgm.path, 'bgm.path');
    const metadata = probe(source);
    if (!metadata.streams.some(s => s.codec_type === 'audio')) fail('bgm.path has no audio stream');
    const offset = number(input.bgm.offset, 0, 0, 86400, 'bgm.offset');
    const sourceDuration = Number(metadata.format.duration);
    if (!Number.isFinite(sourceDuration) || sourceDuration <= offset) fail('bgm.offset must be before the audio ends');
    const loop = input.bgm.loop ?? false;
    if (typeof loop !== 'boolean') fail('bgm.loop must be boolean');
    if (!loop && sourceDuration - offset + 0.01 < duration) fail(`BGM is too short for ${duration}s; supply a longer track or explicitly set bgm.loop=true`);
    const fadeIn = number(input.bgm.fadeIn, 0.4, 0, duration / 2, 'bgm.fadeIn');
    const fadeOut = number(input.bgm.fadeOut, 0.8, 0, duration / 2, 'bgm.fadeOut');
    bgm = { source, path: 'assets/music.wav', volume: number(input.bgm.volume, 0.25, 0, 1, 'bgm.volume'), fadeIn, fadeOut, offset, loop };
  }
  let fontPath = null;
  if (input.font) {
    const source = localFile(input.font, 'font');
    const ext = path.extname(source).toLowerCase();
    if (!['.woff2', '.woff', '.ttf', '.otf'].includes(ext)) fail('font must be WOFF2, WOFF, TTF or OTF');
    fontPath = `assets/font${ext}`;
    filesToCopy.set(fontPath, source);
  }
  const gsapPath = args.gsap ? path.resolve(args.gsap) : path.resolve(HERE, '../templates/vendor/gsap.min.js');
  if (!fs.existsSync(gsapPath)) fail('Local GSAP missing; provide --gsap /path/to/gsap.min.js');
  const checkPath = path.join(HERE, 'check.mjs');
  if (!fs.existsSync(checkPath)) fail('Missing check.mjs beside build.mjs; preserve the complete skill scripts folder');
  fs.mkdirSync(path.join(output, 'assets'), { recursive: true });
  for (const [relative, source] of filesToCopy) fs.copyFileSync(source, path.join(output, relative));
  fs.copyFileSync(gsapPath, path.join(output, 'assets/gsap.min.js'));
  fs.copyFileSync(checkPath, path.join(output, 'check.mjs'));
  const licensePath = path.resolve(HERE, '../templates/vendor/GSAP-LICENSE.txt');
  if (fs.existsSync(licensePath)) fs.copyFileSync(licensePath, path.join(output, 'assets/GSAP-LICENSE.txt'));
  if (bgm) run('ffmpeg', ['-v', 'error', '-y', ...(bgm.loop ? ['-stream_loop', '-1'] : []), '-ss', String(bgm.offset), '-i', bgm.source, '-t', String(duration), '-vn', '-ac', '2', '-ar', '48000', '-c:a', 'pcm_s16le', path.join(output, bgm.path)]);
  const unit = Math.min(width, height);
  const landscape = width > height;
  const safe = { left: 0.07, right: platform === 'tiktok' || platform === 'instagram' ? 0.13 : 0.07, top: 0.08, bottom: platform === 'tiktok' || platform === 'instagram' ? 0.18 : 0.10 };
  const gradeTargets = [];
  const sceneHTML = scenes.map((s, i) => {
    if (style === 'cutout-reveal') {
      const objectPosition = `${round(s.position.x * 100)}% ${round(s.position.y * 100)}%`;
      gradeTargets.push(`#photo-${i}`);
      if (s.cutout && s.leadIn > 0) gradeTargets.push(`#cutout-${i}`);
      return `<img id="photo-${i}" class="clip aligned-photo" data-start="${s.start}" data-duration="${s.duration}" data-track-index="${i * 2}" data-label="Photo ${i + 1}" src="${s.photo.path}" style="object-fit:${s.fit};object-position:${objectPosition};background:${palette.background}" alt="" />
      ${s.cutout && s.leadIn > 0 ? `<img id="cutout-${i}" class="clip aligned-photo reveal" data-start="${round(s.start - s.leadIn)}" data-duration="${s.leadIn}" data-track-index="${i * 2 + 1}" data-label="Cutout ${i + 1}" src="${s.cutout.path}" style="object-fit:${s.fit};object-position:${objectPosition}" alt="" />` : ''}
      ${s.title || s.subtitle ? `<p id="shot-caption-${i}" class="clip shot-caption" data-start="${s.start}" data-duration="${s.duration}" data-track-index="${121 + i}">${html(s.title)}${s.title && s.subtitle ? '\n' : ''}${html(s.subtitle)}</p>` : ''}`;
    }
    const background = s.background ? `<img id="background-${i}" class="scene-background" src="${s.background.path}" alt="" />` : '';
    if (s.background) gradeTargets.push(`#background-${i}`);
    const layers = s.layers.map((l, j) => {
      const lw = round(width * l.widthFraction), lh = round(lw * l.height / l.width);
      gradeTargets.push(`#image-${i}-${j}`);
      return `<div class="layer-box" style="left:${round(l.x * width - lw / 2)}px;top:${round(l.y * height - lh / 2)}px;width:${lw}px;height:${lh}px"><div id="layer-${i}-${j}" class="layer-motion"><img id="image-${i}-${j}" src="${l.path}" width="${l.width}" height="${l.height}" alt="" /></div></div>`;
    }).join('\n');
    const titleSize = round(unit * (s.title.length > 48 ? 0.061 : s.title.length > 28 ? 0.076 : 0.095));
    return `<section id="${s.id}" class="clip scene" data-start="${s.start}" data-duration="${s.duration}" data-track-index="${i}" data-label="${html(s.title || `Scene ${i + 1}`)}">
      <div class="scene-base"></div>${background}${layers}
      ${s.title ? `<div id="copy-${i}" class="headline-box"><p class="scene-count">${String(i + 1).padStart(2, '0')} / ${String(scenes.length).padStart(2, '0')}</p><h1 style="font-size:${titleSize}px">${html(s.title)}</h1><div class="accent-rule"></div></div>` : ''}
      ${s.subtitle ? `<div id="subtitle-${i}" class="subtitle-box"><p>${html(s.subtitle)}</p></div>` : ''}
    </section>`;
  }).join('\n');
  const audioPoints = bgm ? [{ t: 0, v: bgm.fadeIn > 0 ? 0 : bgm.volume }, ...(bgm.fadeIn > 0 ? [{ t: bgm.fadeIn, v: bgm.volume }] : []), ...(bgm.fadeOut > 0 ? [{ t: round(duration - bgm.fadeOut), v: bgm.volume }, { t: duration, v: 0 }] : [{ t: duration, v: bgm.volume }])] : [];
  const audioHTML = bgm ? `<audio id="music-bed" src="${bgm.path}" data-start="0" data-duration="${duration}" data-track-index="100" data-volume="${bgm.volume}" data-automation="${html(JSON.stringify({ version: 1, lanes: [{ target: 'volume', points: audioPoints.filter((p, i, a) => i === 0 || p.t !== a[i - 1].t) }] }))}"></audio>` : '';
  const animation = style === 'editorial' ? scenes.map((s, i) => ({ start: s.start, duration: s.duration, title: Boolean(s.title), subtitle: Boolean(s.subtitle), layers: s.layers.map(l => ({ motion: l.motion, rotation: l.rotation })) })) : [];
  const page = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=${width}, height=${height}"><title>${html(title)}</title>
<script src="assets/gsap.min.js"></script>
<style>
${fontPath ? `@font-face{font-family:CollageFont;src:url('${fontPath}');font-display:block;}` : ''}
.layer-motion,.headline-box,.subtitle-box{opacity:0}
.aligned-photo{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.reveal{z-index:10}.shot-caption,.global-overlay{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;text-align:center;z-index:25;padding:${round(unit * 0.13)}px;pointer-events:none;white-space:pre-line;margin:0;font-family:${fontPath ? 'CollageFont,' : ''}serif;font-size:${round(unit * .042)}px;line-height:1.35;font-weight:400;letter-spacing:.005em;color:#ffffff;text-shadow:0 1px 8px #00000055}.global-overlay{color:${overlay?.color ?? '#ffffff'}}.end-background{position:absolute;inset:0;background:#090909;z-index:40}.end-title,.end-subtitle{position:absolute;left:13%;width:74%;text-align:center;white-space:pre-line;color:#ffffff;z-index:41;margin:0}.end-title{top:35%;height:24%;display:flex;align-items:center;justify-content:center;font-size:${round(unit*.061)}px;font-weight:600;line-height:1.15}.end-subtitle{top:62%;font-size:${round(unit*.032)}px;line-height:1.4}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;background:${palette.background}}body{font-family:${fontPath ? 'CollageFont,' : ''}system-ui,sans-serif;color:${palette.ink}}
#root{position:relative;width:100%;height:100%;overflow:hidden}.scene,.scene-base{position:absolute;inset:0}.scene{overflow:hidden}.scene-base{background:${palette.background}}.scene-background{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.layer-box{position:absolute}.layer-motion{width:100%;height:100%;transform-origin:center center}.layer-motion img{display:block;width:100%;height:100%;object-fit:contain}.headline-box{position:absolute;left:${round(width * safe.left)}px;top:${round(height * safe.top)}px;width:${round(width * (landscape ? 0.51 : 1 - safe.left - safe.right))}px;padding:${round(unit * 0.026)}px;background:${palette.background};color:${palette.ink};z-index:20}.scene-count{font-size:${round(unit * 0.025)}px;line-height:1.4;letter-spacing:.13em;margin:0 0 ${round(unit * 0.025)}px;font-weight:600}h1{margin:0;line-height:1.04;letter-spacing:-.045em;font-weight:850;overflow-wrap:anywhere;white-space:pre-line}.accent-rule{width:${round(unit * 0.11)}px;height:${round(unit * 0.009)}px;background:${palette.accent};margin-top:${round(unit * 0.025)}px}.subtitle-box{position:absolute;left:${round(width * safe.left)}px;bottom:${round(height * safe.bottom)}px;max-width:${round(width * (1 - safe.left - safe.right))}px;background:${palette.background};color:${palette.ink};padding:${round(unit * 0.018)}px ${round(unit * 0.025)}px;z-index:21}.subtitle-box p{margin:0;font-size:${round(unit * 0.032)}px;line-height:1.4;font-weight:550;white-space:pre-line;overflow-wrap:anywhere}
</style></head><body>
<div id="root" data-composition-id="collage-film" data-start="0" data-width="${width}" data-height="${height}" data-duration="${duration}">
${sceneHTML}
${overlay?.text ? `<p id="global-overlay" class="clip global-overlay" data-start="0" data-duration="${pictureDuration}" data-track-index="185">${html(overlay.text)}</p>` : ''}
${endCard ? `<div id="end-background" class="clip end-background" data-start="${pictureDuration}" data-duration="${endCard.duration}" data-track-index="186"></div><h2 id="end-title" class="clip end-title" data-start="${pictureDuration}" data-duration="${endCard.duration}" data-track-index="187">${html(endCard.title)}</h2><p id="end-subtitle" class="clip end-subtitle" data-start="${pictureDuration}" data-duration="${endCard.duration}" data-track-index="188">${html(endCard.subtitle)}</p>` : ''}
${audioHTML}
</div><script>
const scenes = ${scriptJSON(animation)};
const unit = ${unit};
const tl = gsap.timeline({paused:true});
scenes.forEach((scene,i)=>{
  const t=scene.start;
  tl.addLabel('scene-'+i,t);
  if(scene.title) tl.fromTo('#copy-'+i,{y:unit*.035,opacity:0},{y:0,opacity:1,duration:.48,ease:'power3.out',immediateRender:false},t+.03);
  if(scene.subtitle) tl.fromTo('#subtitle-'+i,{y:unit*.025,opacity:0},{y:0,opacity:1,duration:.4,ease:'power2.out',immediateRender:false},t+.48);
  scene.layers.forEach((layer,j)=>{
    const id='#layer-'+i+'-'+j, lag=Math.min(j*.1,.45), enter=t+.06+lag;
    const d=Math.min(.7,scene.duration*.27), r=layer.rotation;
    const from={x:0,y:0,rotation:r,scale:1,opacity:1};
    if(layer.motion==='rise'){from.y=unit*.15;from.rotation=r-6;from.scale=.9;from.opacity=0;}
    if(layer.motion==='slide-left'){from.x=-unit*.24;from.rotation=r-8;from.opacity=0;}
    if(layer.motion==='slide-right'){from.x=unit*.24;from.rotation=r+8;from.opacity=0;}
    if(layer.motion==='float'){from.y=unit*.035;from.scale=.98;from.opacity=0;}
    tl.fromTo(id,from,{x:0,y:0,rotation:r,scale:1,opacity:1,duration:layer.motion==='none'?.001:d,ease:'power3.out',immediateRender:false},enter);
    if(layer.motion==='float'){
      const remaining=Math.max(.2,scene.duration-(enter-t)-d-.15);
      tl.fromTo(id,{y:0,rotation:r},{y:-unit*.022,rotation:r+1.2,duration:remaining,ease:'sine.inOut',immediateRender:false},enter+d);
    }
  });
});
window.__timelines['collage-film']=tl;
</script></body></html>`;
  fs.writeFileSync(path.join(output, 'index.html'), page);
  fs.writeFileSync(path.join(output, 'hyperframes.json'), JSON.stringify({ fps, width, height }, null, 2) + '\n');
  fs.writeFileSync(path.join(output, 'package.json'), JSON.stringify({ name: 'collage-film-project', private: true, version: '1.0.0', scripts: { check: 'node check.mjs', preview: 'npx --yes hyperframes@0.8.127 preview . --background', render: `npx --yes hyperframes@0.8.127 render . --fps ${fps}`, snapshot: 'npx --yes hyperframes@0.8.127 snapshot .' } }, null, 2) + '\n');
  if (GRADES[grade]) {
    const command = args['hf-bin'] ? process.execPath : 'npx';
    const prefix = args['hf-bin'] ? [path.resolve(args['hf-bin'])] : ['--yes', 'hyperframes@0.8.127'];
    for (const selector of gradeTargets) {
      const result = JSON.parse(run(command, [...prefix, 'media-treatment', '--project', output, '--selector', selector, '--grading', JSON.stringify(GRADES[grade]), '--apply', '--json']));
      if (!result.ok) fail(`HyperFrames rejected ${grade} for ${selector}: ${JSON.stringify(result)}`);
    }
  }
  const portable = { schemaVersion: 1, title, style, platform, ratio, fps, grade, palette, ...(overlay ? { overlay } : {}), ...(endCard ? { endCard } : {}), ...(fontPath ? { font: fontPath } : {}), ...(bgm ? { bgm: { path: bgm.path, volume: bgm.volume, fadeIn: bgm.fadeIn, fadeOut: bgm.fadeOut, offset: 0, loop: false } } : {}), scenes: scenes.map(s => style === 'cutout-reveal' ? { duration: s.duration, photo: s.photo.path, ...(s.cutout ? { cutout: s.cutout.path } : {}), leadIn: s.leadIn, position: s.position, fit: s.fit, title: s.title, subtitle: s.subtitle } : { duration: s.duration, title: s.title, subtitle: s.subtitle, ...(s.background ? { background: s.background.path } : {}), layers: s.layers.map(l => ({ path: l.path, x: l.x, y: l.y, width: l.widthFraction, rotation: l.rotation, motion: l.motion })) }) };
  fs.writeFileSync(path.join(output, 'job.resolved.json'), JSON.stringify(portable, null, 2) + '\n');
  const report = { ok: true, project: output, composition: 'index.html', duration, width, height, ratio, fps, platform, style, grade, sceneCount: scenes.length, imageCount: gradeTargets.length, bgm: Boolean(bgm), grading: GRADES[grade], safeArea: safe, assets: [...assetCache.values()], warnings: fontPath ? [] : ['No bundled font was supplied; system fonts depend on the render machine. Supply job.font for portable typography.'], next: `node ${JSON.stringify(path.join(output, 'check.mjs'))} --project ${JSON.stringify(output)}` };
  fs.writeFileSync(path.join(output, 'build-report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report, null, 2));
}
try { main(); } catch (error) { console.error(JSON.stringify({ ok: false, error: error.message })); process.exitCode = 1; }
