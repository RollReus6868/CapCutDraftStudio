import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {CREAM, HEBREW, PANEL, SANS, SERIF, WHITE, rgba, useFonts} from './fonts.js';

const C = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'};
const out = Easing.out(Easing.cubic);
const inOut = Easing.inOut(Easing.cubic);

/**
 * Thẻ từ gốc (TERM) — cùng bố cục với bản Pillow (khung phải, viền nhấn bên phải):
 * nhãn ngôn ngữ · chữ gốc (Hebrew đọc từ phải, quét hiện từ phải sang) · từ phiên âm · nghĩa.
 * Clip bắt đầu đúng lúc đồ họa bắt đầu hiện; 0,40 s là đã rõ (khớp motion "slide_right").
 */
export const Term = ({term = '', orig = '', hebrew = false, label = '', sub = '', lengthSec = 0, style = {}}) => {
  useFonts();
  const frame = useCurrentFrame();
  const {fps, width: w, height: h, durationInFrames} = useVideoConfig();
  const t = frame / fps;
  // tắt mờ xong đúng lúc đồ họa hết giờ (clip có thể dài hơn nửa khung hình)
  const L = Math.min(durationInFrames / fps, lengthSec || durationInFrames / fps);
  const k = style.k || 1.3;
  const acc = style.accent || '#C9A45C';
  const boxA = style.boxAlpha ?? 0.8;

  // clip ngắn thì nén nhịp xuất hiện cho vừa (vẫn kịp tắt mờ ở cuối)
  const f = Math.max(0.35, Math.min(1, (L - 0.35) / 1.45));
  const at = (s) => s * f;
  const fadeOut = interpolate(t, [L - 0.35, L], [1, 0], C);
  const appear = interpolate(t, [0, at(0.4)], [0, 1], C);
  const slide = out(interpolate(t, [0, at(0.6)], [0, 1], C));
  const leave = interpolate(t, [L - 0.35, L], [0, 1], C);
  const dx = (1 - slide) * 0.045 * w + leave * 0.02 * w;

  const bar = out(interpolate(t, [at(0.1), at(0.55)], [0, 1], C));
  const lab = interpolate(t, [at(0.15), at(0.45)], [0, 1], C);
  const wipe = inOut(interpolate(t, [at(0.2), at(0.8)], [0, 1], C));
  const rom = out(interpolate(t, [at(0.45), at(0.85)], [0, 1], C));
  const line = out(interpolate(t, [at(0.7), at(1.05)], [0, 1], C));
  const mean = interpolate(t, [at(0.85), at(1.25)], [0, 1], C);
  // ánh sáng chạy ngang chữ gốc một lần sau khi hiện xong
  const shine = interpolate(t, [at(0.85), at(1.6)], [-0.3, 1.3], C);

  const pad = 30 * k;
  const wipeClip = hebrew ? `inset(-20% 0 -20% ${(1 - wipe) * 100}%)` : `inset(-20% ${(1 - wipe) * 100}% -20% 0)`;

  return (
    <AbsoluteFill>
      <div
        style={{
          position: 'absolute',
          right: w * 0.05,
          top: 0,
          bottom: h * 0.06,
          display: 'flex',
          alignItems: 'center',
          opacity: appear * fadeOut,
          transform: `translateX(${dx}px)`,
        }}
      >
        <div
          style={{
            position: 'relative',
            minWidth: w * 0.24,
            maxWidth: w * 0.34 + pad * 2,
            boxSizing: 'border-box',
            padding: `${pad}px ${pad + 5 * k}px ${pad}px ${pad}px`,
            background: PANEL(boxA),
            borderRadius: 4 * k,
            boxShadow: `0 ${10 * k}px ${40 * k}px rgba(0,0,0,0.35)`,
          }}
        >
          <div
            style={{
              position: 'absolute',
              right: 0,
              top: 0,
              bottom: 0,
              width: 5 * k,
              background: acc,
              transformOrigin: 'center top',
              transform: `scaleY(${bar})`,
            }}
          />
          {label ? (
            <div
              style={{
                fontFamily: SANS,
                fontWeight: 700,
                fontSize: 18 * k,
                letterSpacing: `${0.26 + (1 - lab) * 0.25}em`,
                textTransform: 'uppercase',
                color: acc,
                opacity: lab,
                marginBottom: 14 * k,
                whiteSpace: 'nowrap',
              }}
            >
              {label}
            </div>
          ) : null}
          {orig ? (
            <div style={{position: 'relative', marginBottom: 4 * k, clipPath: wipeClip}}>
              <span
                style={{
                  display: 'inline-block',
                  direction: hebrew ? 'rtl' : 'ltr',
                  unicodeBidi: 'isolate',
                  fontFamily: hebrew ? HEBREW : SERIF,
                  fontWeight: hebrew ? 500 : 600,
                  fontSize: (hebrew ? 50 : 46) * k * 1.15,
                  lineHeight: 1.45,
                  color: CREAM,
                  whiteSpace: 'nowrap',
                  backgroundImage:
                    shine > -0.3 && shine < 1.3
                      ? `linear-gradient(100deg, ${CREAM} ${(shine - 0.15) * 100}%, ${WHITE} ${shine * 100}%, ${CREAM} ${(shine + 0.15) * 100}%)`
                      : 'none',
                  WebkitBackgroundClip: shine > -0.3 && shine < 1.3 ? 'text' : undefined,
                  WebkitTextFillColor: shine > -0.3 && shine < 1.3 ? 'transparent' : undefined,
                }}
              >
                {orig}
              </span>
            </div>
          ) : null}
          <div
            style={{
              fontFamily: SERIF,
              fontWeight: 600,
              fontSize: 52 * k,
              lineHeight: 1.15,
              color: WHITE,
              opacity: rom,
              transform: `translateY(${(1 - rom) * 14 * k}px)`,
              whiteSpace: 'nowrap',
            }}
          >
            {term}
          </div>
          {sub ? (
            <>
              <div
                style={{
                  width: 70 * k,
                  height: Math.max(1, 2 * k),
                  background: rgba(acc, 0.9),
                  margin: `${12 * k}px 0 ${12 * k}px`,
                  transformOrigin: 'left center',
                  transform: `scaleX(${line})`,
                }}
              />
              <div
                style={{
                  fontFamily: SERIF,
                  fontStyle: 'italic',
                  fontWeight: 400,
                  fontSize: 30 * k,
                  lineHeight: 1.25,
                  color: CREAM,
                  opacity: mean,
                  maxWidth: w * 0.34,
                  textWrap: 'balance',
                }}
              >
                {sub}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};
