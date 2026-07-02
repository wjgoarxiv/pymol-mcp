import React from 'react';
import {
  AbsoluteFill,
  Img,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from 'remotion';

const MONO = 'Menlo, "Courier New", monospace';
const SANS = 'system-ui, -apple-system, sans-serif';
const CYAN = '#22d3ee';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const fade = (frame: number, at: number, dur = 12) =>
  interpolate(frame, [at, at + dur], [0, 1], clamp);

// ── Timeline (30fps) ────────────────────────────────────────────────────────
const INTRO_OUT = 66; // intro title card fades out
const WS_IN = 60; // workspace fades in (overlaps intro out)
const SPIN_START = 250; // viewport crossfades framework -> cages
const OUTRO_START = 470;
const N_SPIN = 48;

type Step = {
  appear: number;
  kind: 'user' | 'tool';
  text?: string;
  name?: string;
  args?: string;
  result?: string;
  caption: string;
};

const STEPS: Step[] = [
  {appear: 95, kind: 'user', text: 'Load this clathrate hydrate and show me the cages.', caption: 'You ask in plain language.'},
  {appear: 150, kind: 'tool', name: 'load_structure', args: '"hydrate.gro"', result: '{ object: "hyd", n_atoms: 3264 }', caption: 'load_structure — PyMOL reads the GROMACS .gro, fully headless.'},
  {appear: 222, kind: 'tool', name: 'identify_cages', args: '"hyd"', result: '{ structure_type: "sII", "5^12": 128, "5^12 6^4": 64 }', caption: 'identify_cages — TRACE ring-perception maps the cage lattice.'},
  {appear: 305, kind: 'tool', name: 'mark_cages', args: '"hyd"', result: '{ n_cages: 192, object: "cages" }', caption: 'mark_cages — cages drawn as wireframe polyhedra.'},
  {appear: 372, kind: 'tool', name: 'render_image', args: '', result: '🖼  ray-traced PNG returned inline', caption: 'render_image — the model sees exactly what it drew.'},
];

const typed = (full: string, start: number, frame: number, cps = 1.5) => {
  const n = Math.max(0, Math.floor((frame - start) * cps));
  return {shown: full.slice(0, n), done: n >= full.length};
};

const IntroCard: React.FC<{frame: number; fps: number}> = ({frame, fps}) => {
  const s = spring({frame, fps, config: {damping: 200, mass: 0.8}});
  const scale = interpolate(s, [0, 1], [0.86, 1]);
  const op = interpolate(frame, [0, 14, INTRO_OUT - 14, INTRO_OUT], [0, 1, 1, 0], clamp);
  const sub = fade(frame, 18, 16);
  return (
    <AbsoluteFill style={{opacity: op, alignItems: 'center', justifyContent: 'center'}}>
      <div style={{transform: `scale(${scale})`, textAlign: 'center'}}>
        <div style={{fontFamily: MONO, fontSize: 130, fontWeight: 700, color: 'white', textShadow: `0 0 60px rgba(34,211,238,0.55)`}}>
          pymol-mcp
        </div>
        <div style={{opacity: sub, fontFamily: MONO, fontSize: 34, color: CYAN, marginTop: 20, letterSpacing: 1}}>
          headless PyMOL, driven by your LLM
        </div>
      </div>
    </AbsoluteFill>
  );
};

const UserBubble: React.FC<{text: string; op: number; y: number}> = ({text, op, y}) => (
  <div style={{opacity: op, transform: `translateY(${y}px)`, display: 'flex', justifyContent: 'flex-end', marginBottom: 24}}>
    <div style={{background: 'linear-gradient(135deg,#1e40af,#0891b2)', color: 'white', borderRadius: 18, borderBottomRightRadius: 5, padding: '17px 24px', fontSize: 27, maxWidth: 600, fontFamily: SANS, lineHeight: 1.35, boxShadow: '0 10px 30px rgba(30,64,175,0.35)'}}>
      {text}
    </div>
  </div>
);

const ToolCard: React.FC<{step: Step; op: number; y: number; frame: number}> = ({step, op, y, frame}) => {
  const resStart = step.appear + 10;
  const {shown, done} = typed(step.result ?? '', resStart, frame);
  const blink = Math.floor(frame / 8) % 2 === 0;
  return (
    <div style={{opacity: op, transform: `translateY(${y}px)`, background: '#0f1a30', border: '1px solid #223a5e', borderRadius: 15, padding: '16px 20px', marginBottom: 18, boxShadow: '0 6px 24px rgba(0,0,0,0.28)'}}>
      <div style={{fontFamily: MONO, fontSize: 24, fontWeight: 700, color: CYAN}}>
        <span style={{color: '#3f5f86'}}>▸ </span>
        {step.name}
        <span style={{color: '#61789a'}}>({step.args})</span>
      </div>
      <div style={{fontFamily: MONO, fontSize: 21, color: '#9fd3e4', marginTop: 9, minHeight: 26}}>
        {shown}
        {!done && frame >= resStart && <span style={{opacity: blink ? 1 : 0, color: CYAN}}>▌</span>}
      </div>
    </div>
  );
};

export const Demo: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const wsOp = fade(frame, WS_IN, 20);
  const activeStep = [...STEPS].reverse().find((s) => frame >= s.appear) ?? STEPS[0];

  // Viewport crossfade: framework -> rotating cages
  const spinIdx = Math.floor(Math.max(0, frame - SPIN_START) / 1.4) % N_SPIN;
  const fwOp = interpolate(frame, [SPIN_START - 12, SPIN_START + 8], [1, 0], clamp);
  const capMeta = interpolate(frame, [SPIN_START, SPIN_START + 14], [0, 1], clamp);
  const float = Math.sin(frame / 34) * 5;

  const outro = interpolate(frame, [OUTRO_START, OUTRO_START + 22], [0, 1], clamp);
  const outroScale = spring({frame: frame - OUTRO_START, fps, config: {damping: 200}});

  return (
    <AbsoluteFill style={{background: 'radial-gradient(circle at 30% 20%, #0b1224, #070b16)'}}>
      {frame < INTRO_OUT + 4 && <IntroCard frame={frame} fps={fps} />}

      {/* Workspace */}
      <AbsoluteFill style={{opacity: wsOp}}>
        {/* Header */}
        <div style={{position: 'absolute', top: 0, left: 0, right: 0, height: 104, display: 'flex', alignItems: 'center', paddingLeft: 56, borderBottom: '1px solid #16233f'}}>
          <div style={{fontFamily: MONO, fontSize: 38, fontWeight: 700, color: 'white'}}>pymol-mcp</div>
          <div style={{fontFamily: MONO, fontSize: 21, color: '#5b7089', marginLeft: 22, marginTop: 6}}>headless PyMOL, driven by your LLM</div>
        </div>

        {/* Body split */}
        <div style={{position: 'absolute', top: 104, left: 0, right: 0, bottom: 96, display: 'flex'}}>
          {/* Chat panel */}
          <div style={{width: 800, padding: '38px 44px', overflow: 'hidden'}}>
            {STEPS.map((step, i) => {
              const op = fade(frame, step.appear, 10);
              if (op <= 0) return null;
              const sp = spring({frame: frame - step.appear, fps, config: {damping: 200}});
              const y = interpolate(sp, [0, 1], [24, 0]);
              return step.kind === 'user' ? (
                <UserBubble key={i} text={step.text!} op={op} y={y} />
              ) : (
                <ToolCard key={i} step={step} op={op} y={y} frame={frame} />
              );
            })}
          </div>

          {/* Viewport */}
          <div style={{flex: 1, position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
            <div style={{position: 'relative', width: 920, height: 690, borderRadius: 18, overflow: 'hidden', border: '1px solid #1e3050', background: 'white', boxShadow: '0 24px 90px rgba(6,182,212,0.18)', transform: `translateY(${float}px)`}}>
              <Img src={staticFile(`frames/spin_${String(spinIdx).padStart(3, '0')}.png`)} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain'}} />
              <Img src={staticFile('frames/load.png')} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', opacity: fwOp}} />
              <div style={{position: 'absolute', top: 16, left: 20, fontFamily: MONO, fontSize: 18, color: '#4a6182', opacity: capMeta}}>
                cages · 128× 5¹²  ·  64× 5¹²6⁴
              </div>
            </div>
          </div>
        </div>

        {/* Caption strip */}
        <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 96, background: '#0a1120', borderTop: '1px solid #16233f', display: 'flex', alignItems: 'center', paddingLeft: 56, paddingRight: 56}}>
          <div style={{width: 8, height: 8, borderRadius: 8, background: CYAN, marginRight: 18, boxShadow: `0 0 14px ${CYAN}`}} />
          <div style={{flex: 1, fontFamily: MONO, fontSize: 25, color: '#c4d8e8'}}>{activeStep.caption}</div>
          <div style={{display: 'flex', gap: 12}}>
            {STEPS.map((s, i) => (
              <div key={i} style={{width: 11, height: 11, borderRadius: 11, background: frame >= s.appear ? CYAN : '#243a5c', boxShadow: frame >= s.appear ? `0 0 10px ${CYAN}` : 'none'}} />
            ))}
          </div>
        </div>
      </AbsoluteFill>

      {/* Outro */}
      <AbsoluteFill style={{opacity: outro, background: 'radial-gradient(circle at 50% 45%, #0b1426, #05080f)', alignItems: 'center', justifyContent: 'center'}}>
        <div style={{transform: `scale(${interpolate(outroScale, [0, 1], [0.9, 1])})`, textAlign: 'center'}}>
          <div style={{fontFamily: MONO, fontSize: 96, fontWeight: 700, color: 'white', textShadow: '0 0 60px rgba(34,211,238,0.5)'}}>pymol-mcp</div>
          <div style={{fontFamily: MONO, fontSize: 30, color: CYAN, marginTop: 20}}>GROMACS · LAMMPS · cages · F3/F4 · H-bonds</div>
          <div style={{fontFamily: MONO, fontSize: 23, color: '#61789a', marginTop: 30}}>github.com/wjgoarxiv/pymol-mcp</div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
