import React from 'react';
import {Composition} from 'remotion';
import {Term} from './Term.jsx';
import {Timeline} from './Timeline.jsx';

// Cỡ khung, số khung hình/giây và độ dài do CapCut Draft Studio truyền vào (props).
const meta = ({props}) => ({
  width: props.width || 1920,
  height: props.height || 1080,
  fps: props.fps || 30,
  durationInFrames: Math.max(1, props.frames || 1),
});

const base = {width: 1920, height: 1080, fps: 30, frames: 150, style: {accent: '#C9A45C', boxAlpha: 0.8, k: 1.3}};

export const Root = () => (
  <>
    <Composition
      id="Term"
      component={Term}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={150}
      calculateMetadata={meta}
      defaultProps={{...base, term: 'Nephilim', orig: 'נְפִילִים', hebrew: true, label: 'Hebrew', sub: 'the fallen ones'}}
    />
    <Composition
      id="Timeline"
      component={Timeline}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={180}
      calculateMetadata={meta}
      defaultProps={{
        ...base,
        frames: 180,
        label: 'Key dates',
        subsOn: false,
        points: [
          {label: '1446 BC', cur: false},
          {label: '586 BC', cur: true},
          {label: '70 AD', cur: false},
        ],
      }}
    />
  </>
);
