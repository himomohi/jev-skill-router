"""Separate storyboard preview renderer, NOT Remotion. Requires Pillow and FFmpeg."""
from __future__ import annotations
import argparse
import json
import shutil
import subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
W,H,FPS,SECONDS=1280,720,24,30
BG='#071219';PANEL='#13242d';INK='#eef5f4';MUTED='#94adb5';ACCENT='#72e3c4';LINE='#2a414c'
METRIC=next(r for r in json.loads((ROOT/'docs/benchmark.json').read_text())['results'] if r['skills']==200)
COPY={
'en':{
 'title':['Your skills belong in a library.\nNot in every prompt.','Jev decides. Your agent acts.','200 skills. Same loaded body.','Install. Connect. Remove duplicates.','Less context.\nNo invented guarantees.'],
 'sub':['External catalog. One MCP tool. Only the instructions you need.','Rank metadata, verify evidence, then load selected instructions.','One synthetic, skill-related main-model context. UTF-8 bytes.','Keep trusted skills outside native discovery. Start a new session.','A smaller selection inventory is useful. Honest boundaries matter.'],
 'library':'EXTERNAL LIBRARY  /  200 SKILLS','model':'MAIN MODEL','selected':'SELECTED SKILL',
 'before':'Progressive baseline','after':'Router + same body','reduction':'smaller skill-related payload',
 'flow':['Focused task','Jev: rank','Jev: verify','Load skill','Host acts'],
 'flow_note':'Small catalogs usually need 2 logical API calls; large catalogs add shards.',
 'steps':['Python 3.11+ and a TypeSafe key for live mode','One trusted library for several local harnesses','Dry run first. Apply explicitly. Restore when needed.'],
 'limits':['Read-only routing','Live quality unverified','Not a cost benchmark'],
 'disclaimer':'Synthetic bytes are not model tokens, billed cost, or end-to-end speed.',
 'footer':'Local preview renderer: Pillow + FFmpeg  /  Remotion source included',
 'end':'Jev Skill Router   /   English + Korean   /   MIT'},
'ko':{
 'title':['스킬은 보관소에.\n프롬프트는 필요한 것만.','Jev가 고르고, 에이전트가 실행합니다.','스킬 200개, 같은 본문으로 비교합니다.','설치하고 연결하고, 중복 노출을 끕니다.','더 작은 컨텍스트.\n과장 없는 검증.'],
 'sub':['전체 목록은 외부에. MCP 도구는 하나만. 필요한 지침만 전달합니다.','목록에서 후보 선정 → 지침으로 재검증 → 선택된 본문 로딩','메인 모델의 스킬 관련 데이터 한 묶음. 합성 UTF-8 바이트 비교입니다.','기존 스킬의 기본 노출을 끄고 새 세션에서 확인하세요.','목록은 줄이고, 측정 범위와 미검증 항목은 명확하게 남깁니다.'],
 'library':'외부 스킬 보관소  /  스킬 200개','model':'메인 모델','selected':'선택된 스킬만 전달',
 'before':'기존 점진적 로딩','after':'라우터 + 같은 본문','reduction':'스킬 관련 데이터 감소',
 'flow':['작업 설명','Jev 후보 선정','Jev 재검증','본문 로딩','기존 도구 실행'],
 'flow_note':'작은 목록은 보통 논리적 API 요청 2회, 큰 목록은 분할 호출이 추가됩니다.',
 'steps':['Python 3.11+ · 라이브 모드는 TypeSafe API 키 필요','외부 라이브러리 하나를 여러 로컬 하네스에 연결','이동 계획 확인 → 명시적 적용 → 필요할 때 복구'],
 'limits':['실행 권한은 기존 하네스','라이브 품질은 미검증','비용·속도 측정이 아님'],
 'disclaimer':'합성 바이트 비교입니다. 실제 모델 토큰·과금·작업 속도와 다릅니다.',
 'footer':'별도 미리보기 렌더러: Pillow + FFmpeg  /  Remotion 소스 포함',
 'end':'Jev Skill Router   /   English + 한국어   /   MIT'}
}


def locate_font(lang:str,custom:str|None)->str:
    if custom:
        if not Path(custom).is_file():raise ValueError('Font path does not exist')
        return custom
    candidates=(['/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                 '/usr/share/fonts/truetype/nanum/NanumGothic.ttf','C:/Windows/Fonts/malgun.ttf',
                 '/System/Library/Fonts/AppleSDGothicNeo.ttc'] if lang=='ko' else [])+[
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','/System/Library/Fonts/Supplemental/Arial.ttf','C:/Windows/Fonts/arial.ttf']
    for path in candidates:
        if Path(path).is_file():return path
    raise ValueError('Pass --font with an installed font path.')


def make_scenes(lang:str,font_path:str):
    t=COPY[lang];fonts={}
    def font(size):
        if size not in fonts:fonts[size]=ImageFont.truetype(font_path,size)
        return fonts[size]
    def text(draw,xy,value,size=24,color=INK,max_width=None):
        while max_width and draw.textbbox((0,0),value,font=font(size))[2]>max_width and size>14:size-=1
        draw.text(xy,value,font=font(size),fill=color,spacing=8)
    def box(draw,rect,outline=LINE):draw.rounded_rectangle(rect,radius=20,fill=PANEL,outline=outline,width=2)
    scenes=[]
    for index in range(5):
        image=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(image)
        text(d,(60,33),'JEV SKILL ROUTER',21,ACCENT)
        text(d,(780,37),'EXTERNAL CATALOG / SELECTIVE LOADING',16,MUTED,max_width=440)
        text(d,(60,105),t['title'][index],58 if index in (0,4) else 45,max_width=1160)
        text(d,(60,267 if index in (0,4) else 180),t['sub'][index],22,MUTED,max_width=1160)
        if index==0:
            box(d,(60,330,805,596));box(d,(833,330,1220,596))
            text(d,(86,351),t['library'],19,MUTED)
            for i in range(200):
                x=87+(i%20)*34;y=399+(i//20)*17
                d.rounded_rectangle((x,y,x+25,y+10),radius=3,fill=LINE)
            text(d,(865,354),t['model'],19,MUTED)
            text(d,(859,395),'1 MCP',76,ACCENT)
            text(d,(865,514),t['selected'],22,max_width=326)
        elif index==1:
            for i,name in enumerate(t['flow']):
                left=60+i*236;box(d,(left,286,left+216,482))
                text(d,(left+20,307),f'0{i+1}',31,ACCENT)
                text(d,(left+19,391),name,23,max_width=179)
            text(d,(60,523),t['flow_note'],22,MUTED,max_width=1160)
            text(d,(60,574),'Choice → Noul + Score → confidence gate',23,ACCENT)
        elif index==2:
            box(d,(60,270,838,553));box(d,(864,270,1220,553))
            text(d,(89,294),t['before'],23)
            text(d,(581,294),f"{METRIC['progressive_baseline_bytes']:,} B",24,max_width=231)
            text(d,(89,418),t['after'],23)
            text(d,(602,418),f"{METRIC['routed_main_bytes']:,} B",24,max_width=210)
            text(d,(888,328),f"{METRIC['one_context_reduction_percent']}%",73,ACCENT,max_width=310)
            text(d,(890,435),t['reduction'],21,max_width=306)
            text(d,(60,582),t['disclaimer'],21,MUTED,max_width=1160)
        elif index==3:
            box(d,(60,255,1220,432))
            text(d,(84,279),'$ python Install.py --client codex --root ~/.agents/skills',25,ACCENT,max_width=1090)
            text(d,(84,324),'$ jev-skills park ~/.agents/skills',24,max_width=1090)
            text(d,(84,368),'$ jev-skills park ~/.agents/skills --apply',24,max_width=1090)
            for i,step in enumerate(t['steps']):text(d,(72,461+i*42),step,23,MUTED,max_width=1120)
        else:
            for i,label in enumerate(t['limits']):
                left=60+i*394;box(d,(left,336,left+374,455))
                text(d,(left+20,375),label,23,ACCENT,max_width=334)
            text(d,(60,505),t['end'],28,max_width=1160)
            text(d,(60,565),t['disclaimer'],21,MUTED,max_width=1160)
        text(d,(60,665),t['footer'],15,MUTED,max_width=1040)
        text(d,(1160,665),f'{index+1} / 5',15,MUTED)
        scenes.append(image)
    return scenes


def render(lang:str,out:Path,font_path:str):
    scenes=make_scenes(lang,font_path);black=Image.new('RGB',(W,H),BG)
    out.parent.mkdir(parents=True,exist_ok=True)
    command=['ffmpeg','-y','-loglevel','error','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24',
             '-s',f'{W}x{H}','-r',str(FPS),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast',
             '-crf','21','-pix_fmt','yuv420p','-movflags','+faststart',str(out)]
    with subprocess.Popen(command,stdin=subprocess.PIPE) as process:
        assert process.stdin is not None
        for frame in range(SECONDS*FPS):
            scene=frame//(6*FPS);local=frame%(6*FPS);image=scenes[scene].copy();d=ImageDraw.Draw(image)
            progress=max(0,min(1,(local-10)/40));ease=1-(1-progress)**3
            if scene==0:
                active=min(199,int(ease*199)) if local<75 else 43
                x=87+(active%20)*34;y=399+(active//20)*17
                d.rounded_rectangle((x,y,x+25,y+10),radius=3,fill=ACCENT)
            elif scene==1:
                for i in range(min(4,local//22)+1):
                    left=60+i*236;d.rounded_rectangle((left,286,left+216,482),radius=20,outline=ACCENT,width=3)
            elif scene==2:
                for y,length,color in [(353,718,LINE),(477,718*METRIC['routed_main_bytes']/METRIC['progressive_baseline_bytes'],ACCENT)]:
                    width=max(2,int(length*ease));d.rounded_rectangle((89,y,89+width,y+30),radius=min(8,width//2),fill=color)
            d.rectangle((0,715,int((frame+1)/(SECONDS*FPS)*W),719),fill=ACCENT)
            alpha=min(1,local/9,(143-local)/7)
            if alpha<1:image=Image.blend(black,image,max(0,alpha))
            if scene==2 and local==85:image.save(out.parent/f'poster.{lang}.png')
            process.stdin.write(image.tobytes())
        process.stdin.close()
        if process.wait()!=0:raise RuntimeError('FFmpeg rendering failed')
    return out

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lang',choices=['en','ko'],default='en');parser.add_argument('--font');parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    if not shutil.which('ffmpeg'):parser.error('FFmpeg must be on PATH')
    target=args.out or ROOT/'docs/media'/f'preview.{args.lang}.mp4'
    print(render(args.lang,target,locate_font(args.lang,args.font)))
