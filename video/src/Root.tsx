import React from 'react';
import {Composition} from 'remotion';
import {Demo} from './Demo';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="PymolMcpDemo"
      component={Demo}
      durationInFrames={560}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
