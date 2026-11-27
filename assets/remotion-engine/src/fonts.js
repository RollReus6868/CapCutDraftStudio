import {useEffect, useState} from 'react';
import {cancelRender, continueRender, delayRender, staticFile} from 'remotion';

// Phông TTF lấy từ assets/overlay-fonts của tool (tool chép vào public/fonts lúc cài),
// cùng phông với đồ họa chữ vẽ bằng Pillow nên hai loại nhìn đồng bộ.
// Tiếng Hy Lạp: EB Garamond (fontsource, OFL) — phông TTF của tool không có chữ Hy Lạp.
const GREEK = 'U+0370-03FF,U+1F00-1FFF';
const FACES = [
  ['CDS Serif', 600, 'normal', 'EBGaramond-SemiBold.ttf', null],
  ['CDS Serif', 600, 'normal', 'eb-garamond-greek-600-normal.woff2', 'U+0370-03FF'],
  ['CDS Serif', 600, 'normal', 'eb-garamond-greek-ext-600-normal.woff2', 'U+1F00-1FFF'],
  ['CDS Serif', 400, 'italic', 'EBGaramond-Italic.ttf', null],
  ['CDS Serif', 400, 'italic', 'eb-garamond-greek-400-italic.woff2', 'U+0370-03FF'],
  ['CDS Serif', 400, 'italic', 'eb-garamond-greek-ext-400-italic.woff2', 'U+1F00-1FFF'],
  ['CDS Sans', 700, 'normal', 'Montserrat-Bold.ttf', null],
  ['CDS Sans', 800, 'normal', 'Montserrat-ExtraBold.ttf', null],
  ['CDS Hebrew', 500, 'normal', 'NotoSerifHebrew.ttf', null],
];

export const SERIF = '"CDS Serif", serif';
export const SANS = '"CDS Sans", sans-serif';
export const HEBREW = '"CDS Hebrew", "CDS Serif", serif';
export const GREEK_RANGE = GREEK;

/** Nạp phông xong mới cho vẽ khung hình; thiếu phông thì dừng hẳn (không lặng lẽ dùng phông khác). */
export const useFonts = () => {
  const [handle] = useState(() => delayRender('Đang nạp phông'));
  useEffect(() => {
    const css = FACES.map(([family, weight, style, file, range]) => {
      const fmt = file.endsWith('.woff2') ? 'woff2' : 'truetype';
      return (
        `@font-face{font-family:'${family}';font-weight:${weight};font-style:${style};` +
        `src:url(${staticFile('fonts/' + file)}) format('${fmt}');` +
        (range ? `unicode-range:${range};` : '') +
        `}`
      );
    }).join('\n');
    const el = document.createElement('style');
    el.textContent = css;
    document.head.appendChild(el);
    Promise.all([
      document.fonts.load('600 60px "CDS Serif"', 'Abc ạ'),
      document.fonts.load('600 60px "CDS Serif"', 'λόγος'),
      document.fonts.load('italic 400 60px "CDS Serif"', 'Abc'),
      document.fonts.load('700 30px "CDS Sans"', 'ABC'),
      document.fonts.load('800 30px "CDS Sans"', 'ABC'),
      document.fonts.load('500 60px "CDS Hebrew"', 'נְפִילִים'),
    ])
      .then((sets) => {
        const missing = sets.findIndex((s) => s.length === 0);
        if (missing >= 0) {
          cancelRender(new Error('Thiếu phông số ' + missing + ' trong public/fonts'));
          return;
        }
        continueRender(handle);
      })
      .catch((e) => cancelRender(e));
    return () => el.remove();
  }, [handle]);
};

/** '#C9A45C' → 'rgba(201,164,92,a)' */
export const rgba = (hex, a) => {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '').trim());
  const v = m ? parseInt(m[1], 16) : 0xc9a45c;
  return `rgba(${(v >> 16) & 255},${(v >> 8) & 255},${v & 255},${a})`;
};

export const WHITE = 'rgb(246,241,232)';
export const CREAM = 'rgb(226,214,190)';
export const PANEL = (a) => `rgba(14,12,10,${a})`;
