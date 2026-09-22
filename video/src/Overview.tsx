import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import report from '../../docs/benchmark.json';

const C={bg:'#071219',panel:'#13242d',ink:'#eef5f4',muted:'#94adb5',accent:'#72e3c4',line:'#2a414c'};
const metric=report.results.find(r=>r.skills===200)!;
const clamp={extrapolateLeft:'clamp',extrapolateRight:'clamp'} as const;
type Language='en'|'ko';
const copy={
  en:{titles:['Your skills belong in a library.\nNot in every prompt.','Jev decides. Your agent acts.','200 skills. Same loaded body.','Install. Connect. Remove duplicates.','Less context.\nNo invented guarantees.'],
    subtitles:['External catalog. One MCP tool. Only the instructions you need.','Rank metadata → verify evidence → load selected instructions.','One synthetic, skill-related main-model context. UTF-8 bytes.','Keep your trusted library outside native discovery. Start a new session.','A smaller selection inventory is useful. Honest boundaries matter.'],
    library:'EXTERNAL LIBRARY',main:'MAIN MODEL',selected:'SELECTED SKILL',before:'Progressive baseline',after:'Router + same body',
    reduction:'smaller skill-related payload',labels:['Focused task','Jev: rank','Jev: verify','Load skill','Host acts'],
    note:'Small catalogs usually need 2 logical API calls; larger catalogs add shards.',
    steps:['Python 3.11+ · TypeSafe key for live mode','One library for several local harnesses','Dry-run relocation + explicit apply + restore'],
    limits:['Read-only routing','Live quality unverified','Not a cost benchmark'],
    end:'Jev Skill Router  /  English + Korean  /  MIT',
    disclaimer:'Synthetic bytes ≠ model tokens, billed cost, or end-to-end speed.'},
  ko:{titles:['스킬은 보관소에.\n프롬프트는 필요한 것만.','Jev가 고르고, 에이전트가 실행합니다.','스킬 200개, 같은 본문으로 비교합니다.','설치하고 연결하고, 중복 노출을 끕니다.','더 작은 컨텍스트.\n과장 없는 검증.'],
    subtitles:['전체 목록은 외부에. MCP 도구는 하나만. 필요한 지침만 전달합니다.','목록에서 후보 선정 → 지침으로 적합도 검증 → 선택된 본문 로딩','메인 모델의 스킬 관련 데이터 한 묶음. 합성 UTF-8 바이트 비교입니다.','기존 스킬의 기본 노출을 끄고 새 세션에서 확인하세요.','목록은 줄이고, 측정 범위와 미검증 항목은 명확하게 남깁니다.'],
    library:'외부 스킬 보관소',main:'메인 모델',selected:'선택된 스킬',before:'기존 점진적 로딩',after:'라우터 + 같은 본문',
    reduction:'스킬 관련 데이터 감소',labels:['작업 설명','Jev 후보 선정','Jev 재검증','본문 로딩','기존 도구 실행'],
    note:'작은 목록은 보통 논리적 API 요청 2회, 큰 목록은 분할 호출이 추가됩니다.',
    steps:['Python 3.11+ · 라이브 모드는 TypeSafe 키 필요','외부 라이브러리 하나를 여러 로컬 하네스에 연결','이동 계획 확인 → 명시적 적용 → 필요할 때 복구'],
    limits:['실행 권한은 기존 하네스','라이브 품질은 미검증','비용·속도 측정이 아님'],
    end:'Jev Skill Router  /  English + 한국어  /  MIT',
    disclaimer:'합성 바이트 비교입니다. 실제 모델 토큰·과금·작업 속도와 다릅니다.'}
};
const Box:React.FC<{children:React.ReactNode;style?:React.CSSProperties}>=({children,style})=>
  <div style={{background:C.panel,border:`1px solid ${C.line}`,borderRadius:20,padding:28,...style}}>{children}</div>;

export const Overview:React.FC<{lang:Language}>=({lang})=>{
  const frame=useCurrentFrame();
  const scene=Math.min(4,Math.floor(frame/144));
  const local=frame-scene*144;
  const t=copy[lang];
  const p=interpolate(local,[15,65],[0,1],clamp);
  return <AbsoluteFill style={{background:C.bg,color:C.ink,fontFamily:'Inter, Noto Sans CJK KR, Segoe UI, sans-serif'}}>
    <div style={{position:'absolute',left:60,top:38,fontSize:20,fontWeight:700,letterSpacing:2}}>JEV <span style={{color:C.accent}}>SKILL ROUTER</span></div>
    <div style={{position:'absolute',right:60,top:42,fontSize:15,color:C.muted}}>EXTERNAL CATALOG / SELECTIVE LOADING</div>
    <div style={{position:'absolute',left:60,right:60,top:110,opacity:interpolate(local,[0,10,137,143],[0,1,1,0],clamp)}}>
      <div style={{fontSize:scene===0||scene===4?62:46,fontWeight:750,lineHeight:1.17,whiteSpace:'pre-line',letterSpacing:-1.5}}>{t.titles[scene]}</div>
      <div style={{marginTop:19,fontSize:22,color:C.muted,maxWidth:1150,lineHeight:1.5}}>{t.subtitles[scene]}</div>
      {scene===0&&<div style={{display:'flex',gap:26,marginTop:35}}>
        <Box style={{width:700}}><div style={{fontSize:17,color:C.muted,marginBottom:17}}>{t.library} / 200 SKILLS</div>
          <div style={{display:'grid',gridTemplateColumns:'repeat(20, 1fr)',gap:7}}>{Array.from({length:200},(_,i)=><div key={i} style={{height:10,borderRadius:3,background:i===43?C.accent:C.line,opacity:interpolate(local,[i*.10,20+i*.1],[.1,1],clamp)}} />)}</div>
        </Box>
        <Box style={{width:335,display:'flex',flexDirection:'column',justifyContent:'center'}}>
          <div style={{color:C.muted,fontSize:17}}>{t.main}</div><div style={{fontSize:60,fontWeight:800,color:C.accent,marginTop:6}}>1 MCP</div><div style={{fontSize:21}}>{t.selected}</div>
        </Box>
      </div>}
      {scene===1&&<>
        <div style={{display:'flex',gap:14,marginTop:66}}>{t.labels.map((name,i)=><Box key={name} style={{width:219,height:160,padding:20,borderColor:local>i*16?C.accent:C.line,opacity:interpolate(local,[i*12,i*12+15],[.2,1],clamp)}}><div style={{color:C.accent,fontSize:30,marginBottom:26}}>0{i+1}</div><div style={{fontSize:23,fontWeight:600}}>{name}</div></Box>)}</div>
        <div style={{fontSize:22,color:C.muted,marginTop:30}}>{t.note}</div>
      </>}
      {scene===2&&<>
        <div style={{display:'flex',gap:24,marginTop:32}}>
          <Box style={{width:770}}>
            <div style={{display:'flex',justifyContent:'space-between',fontSize:21}}><span>{t.before}</span><strong>{metric.progressive_baseline_bytes.toLocaleString('en-US')} B</strong></div>
            <div style={{height:31,background:C.line,borderRadius:8,marginTop:12,width:Math.max(1,p*100)+'%'}} />
            <div style={{display:'flex',justifyContent:'space-between',fontSize:21,marginTop:34}}><span>{t.after}</span><strong>{metric.routed_main_bytes.toLocaleString('en-US')} B</strong></div>
            <div style={{height:31,background:C.accent,borderRadius:8,marginTop:12,width:Math.max(1,p*100*metric.routed_main_bytes/metric.progressive_baseline_bytes)+'%'}} />
          </Box>
          <Box style={{width:365,display:'flex',flexDirection:'column',justifyContent:'center'}}><div style={{fontSize:71,fontWeight:800,color:C.accent}}>{metric.one_context_reduction_percent}%</div><div style={{fontSize:21,lineHeight:1.45}}>{t.reduction}</div></Box>
        </div>
        <div style={{fontSize:20,color:C.muted,marginTop:26}}>{t.disclaimer}</div>
      </>}
      {scene===3&&<>
        <Box style={{marginTop:33,fontFamily:'ui-monospace, Consolas, monospace',fontSize:22,lineHeight:1.8}}>
          <div style={{color:C.accent}}>$ python Install.py --client codex --root ~/.agents/skills</div>
          <div>$ jev-skills park ~/.agents/skills</div>
          <div>$ jev-skills park ~/.agents/skills --apply</div>
        </Box>
        <div style={{marginTop:22,fontSize:21,color:C.muted,lineHeight:1.8}}>{t.steps.map(s=><div key={s}>{s}</div>)}</div>
      </>}
      {scene===4&&<>
        <div style={{display:'flex',gap:18,marginTop:35}}>{t.limits.map(s=><Box key={s} style={{width:370,fontSize:24,color:C.accent}}>{s}</Box>)}</div>
        <div style={{marginTop:38,fontSize:27}}>{t.end}</div>
      </>}
    </div>
    <div style={{position:'absolute',bottom:39,left:60,color:C.muted,fontSize:15}}>Remotion composition · Measured synthetic payload · Not a live product recording</div>
    <div style={{position:'absolute',right:60,bottom:39,fontSize:15,color:C.muted}}>{scene+1} / 5</div>
    <div style={{position:'absolute',bottom:0,left:0,height:5,background:C.accent,width:interpolate(frame,[0,719],[0,1280],clamp)}} />
  </AbsoluteFill>;
};
