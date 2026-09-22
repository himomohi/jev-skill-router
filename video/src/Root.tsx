import React from 'react';
import {Composition} from 'remotion';
import {Overview} from './Overview';
export const Root: React.FC = () => <>
  <Composition id="OverviewEN" component={Overview} width={1280} height={720} fps={24} durationInFrames={720} defaultProps={{lang:'en' as const}} />
  <Composition id="OverviewKO" component={Overview} width={1280} height={720} fps={24} durationInFrames={720} defaultProps={{lang:'ko' as const}} />
</>;
