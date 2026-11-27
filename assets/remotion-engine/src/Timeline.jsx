import React from 'react';
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {CREAM, PANEL, SANS, WHITE, rgba, useFonts} from './fonts.js';

const C = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'};
const out = Easing.out(Easing.cubic);

/**
 * Dòng thời gian (TIMELINE) — cùng chỗ với bản Pillow (0,80 chiều cao, 0,70 khi có phụ đề):
 * nền tối mờ dần, vạch nhấn chạy từ trái, mỗi mốc bật ra khi vạch tới, mốc đang nói sáng nhịp.
 */
export const Timeline = ({points = [], label = '', subsOn = false, lengthSec = 0, style = {}}) => {
  useFonts();
  const frame = useCurrentFrame();
  const {fps, width: w, height: h, durationInFrames} = useVideoConfig();
  const t = frame / fps;
  // tắt mờ xong đúng lúc đồ họa hết giờ (clip có thể dài hơn nửa khung hình)
  const L = Math.min(durationInFrames / fps, lengthSec || durationInFrames / fps);
  const k = style.k || 1.3;
  const acc = style.accent || '#C9A45C';

  const cy = h * (subsOn ? 0.7 : 0.8);
  const x0 = w * 0.1;
  const x1 = w * 0.9;
  const n = Math.max(1, points.length);

  const f = Math.max(0.35, Math.min(1, (L - 0.35) / 2.0));
  const fadeOut = interpolate(t, [L - 0.35, L], [1, 0], C);
  const bg = interpolate(t, [0, 0.4 * f], [0, 1], C);
  const w0 = 0.3 * f;
  const dur = Math.min(1.4, Math.max(0.4, (L - w0) * 0.5)) * f;
  const prog = out(interpolate(t, [w0, w0 + dur], [0, 1], C));
  const xe = x0 + (x1 - x0) * prog;
  const lab = interpolate(t, [0.15 * f, 0.5 * f], [0, 1], C);

  const lw = Math.max(2, 3 * k);
  const top = cy - h * 0.2;
  const bottom = Math.min(h, cy + h * 0.22);

  return (
    <AbsoluteFill style={{opacity: fadeOut}}>
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top,
          height: bottom - top,
          opacity: bg,
          background: `linear-gradient(to bottom, ${PANEL(0)}, ${PANEL(0.75)})`,
        }}
      />
      {label ? (
        <div
          style={{
            position: 'absolute',
            left: x0,
            top: cy - 92 * k,
            fontFamily: SANS,
            fontWeight: 700,
            fontSize: 19 * k,
            letterSpacing: `${0.26 + (1 - lab) * 0.2}em`,
            textTransform: 'uppercase',
            color: acc,
            opacity: lab * bg,
            whiteSpace: 'nowrap',
          }}
        >
          {label}
        </div>
      ) : null}
      {/* vạch nền mờ + vạch nhấn chạy */}
      <div
        style={{
          position: 'absolute',
          left: x0,
          top: cy - lw / 2,
          width: x1 - x0,
          height: lw,
          background: `rgba(226,214,190,${(70 / 255) * bg})`,
          borderRadius: lw,
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: x0,
          top: cy - lw / 2,
          width: Math.max(0, xe - x0),
          height: lw,
          background: acc,
          borderRadius: lw,
          boxShadow: `0 0 ${10 * k}px ${rgba(acc, 0.55)}`,
        }}
      />
      {points.map((p, i) => {
        const px = x0 + (x1 - x0) * ((i + 0.5) / n);
        const reach = w0 + dur * Math.min(1, ((i + 0.5) / n) ** 0.6);
        const pop = spring({frame: frame - Math.round(reach * fps), fps, config: {damping: 10, stiffness: 160}});
        const r = (p.cur ? 11 : 7) * k * pop;
        const pulse = p.cur ? 0.5 + 0.5 * Math.sin((t - reach) * Math.PI * 1.6) : 0;
        const glow = p.cur ? r * (1.9 + 0.5 * pulse) : 0;
        const above = i % 2 === 0;
        const fs = (p.cur ? 30 : 26) * k;
        const txt = interpolate(pop, [0, 0.7], [0, 1], C);
        return (
          <React.Fragment key={i}>
            {p.cur ? (
              <div
                style={{
                  position: 'absolute',
                  left: px - glow,
                  top: cy - glow,
                  width: glow * 2,
                  height: glow * 2,
                  borderRadius: '50%',
                  background: rgba(acc, 0.22 + 0.12 * pulse),
                }}
              />
            ) : null}
            <div
              style={{
                position: 'absolute',
                left: px - r,
                top: cy - r,
                width: r * 2,
                height: r * 2,
                boxSizing: 'border-box',
                borderRadius: '50%',
                background: p.cur ? acc : CREAM,
                border: `${Math.max(1, 2 * k)}px solid ${PANEL(1)}`,
              }}
            />
            <div
              style={{
                position: 'absolute',
                left: px - 300 * k,
                width: 600 * k,
                textAlign: 'center',
                top: above ? cy - 11 * k - 14 * k - fs * 1.25 : cy + 11 * k + 12 * k,
                fontFamily: SANS,
                fontWeight: p.cur ? 800 : 700,
                fontSize: fs,
                lineHeight: 1.25,
                color: p.cur ? acc : WHITE,
                opacity: txt,
                transform: `translateY(${(1 - txt) * (above ? 10 : -10) * k}px)`,
                textShadow: `0 ${2 * k}px ${8 * k}px rgba(0,0,0,0.5)`,
                whiteSpace: 'nowrap',
              }}
            >
              {p.label}
            </div>
          </React.Fragment>
        );
      })}
    </AbsoluteFill>
  );
};
