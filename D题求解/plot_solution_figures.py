# 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
"""由正式求解数据绘制解题图；NATURE_FIGURE_SCRIPTS 指向已安装的绘图检查工具。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
if (ROOT/'.figure-deps').is_dir():sys.path.insert(0,str(ROOT/'.figure-deps'))
QA=Path(os.environ['NATURE_FIGURE_SCRIPTS'])
sys.path.insert(0,str(QA))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
from audit_panel_alignment import require_matplotlib_panel_alignment
from d_common import Terrain,DEM

plt.rcParams['font.family']='sans-serif'
plt.rcParams['font.sans-serif']=['Microsoft YaHei','DejaVu Sans']
plt.rcParams.update({'svg.fonttype': 'none', 'pdf.fonttype': 42})
plt.rcParams.update({'font.size':8,'axes.titlesize':9,'axes.labelsize':8,
                     'xtick.labelsize':7,'ytick.labelsize':7,'legend.fontsize':7,
                     'axes.spines.top':False,'axes.spines.right':False,
                     'axes.linewidth':0.6,'legend.frameon':False,'axes.unicode_minus':False})
font_manager.findfont('Microsoft YaHei',fallback_to_default=False)
OUT=ROOT/'交付材料'/'figures'
OUT.mkdir(exist_ok=True)
BLUE='#27669B';ORANGE='#BE6928';GRAY='#D1D5DA'


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def finish(fig,ax,name,data,exclude=()):
    fig.canvas.draw()
    require_matplotlib_panel_alignment(fig,axes=[ax],exclude_axes=list(exclude),
                                       json_out=str(OUT/f'{name}.alignment.json'),strict=True)
    fig.savefig(OUT/f'{name}.svg')
    fig.savefig(OUT/f'{name}.pdf')
    fig.savefig(OUT/f'{name}.png',dpi=300)
    plt.close(fig)
    write(OUT/f'{name}.data.json',data)
    env=os.environ.copy()
    env['PYTHONPATH']=str(ROOT/'.figure-deps')+os.pathsep+env.get('PYTHONPATH','')
    runs=[('text',[str(QA/'audit_pdf_text.py'),str(OUT/f'{name}.pdf'),'--min-pt','5','--json']),
          ('collision',[str(QA/'audit_figure_collisions.py'),str(OUT/f'{name}.pdf'),
                        '--json-out',str(OUT/f'{name}.collision.json'),
                        '--overlay-pdf',str(OUT/f'{name}.collision.pdf')])]
    for label,args in runs:
        done=subprocess.run([sys.executable,'-X','utf8',*args],env=env,capture_output=True,text=True,encoding='utf-8')
        if label=='text':(OUT/f'{name}.text.json').write_text(done.stdout,encoding='utf-8')
        print(name,label,'exit',done.returncode,done.stdout[-900:],flush=True)
        if done.returncode!=0:raise RuntimeError(f'{name} {label}: {done.stderr}')


def canvas(height=110):
    width_inches=180/25.4
    fig,ax=plt.subplots(figsize=(width_inches,height/25.4))
    fig.subplots_adjust(left=.13,right=.95,bottom=.16,top=.88)
    return fig,ax


def terrain_map(s):
    t=Terrain();nodes={n['id']:n for n in s['nodes']}
    sites={(r['lon'],r['lat']) for r in s['q3_relay_sorties']}
    points=[(n['lon'],n['lat']) for n in nodes.values()]+list(sites)
    xs,ys=zip(*points)
    corners=[t.pixel(min(xs)-.015,max(ys)+.015),t.pixel(max(xs)+.015,min(ys)-.015)]
    c0=max(0,int(np.floor(corners[0][0])));c1=min(t.width,int(np.ceil(corners[1][0])))
    r0=max(0,int(np.floor(corners[0][1])));r1=min(t.height,int(np.ceil(corners[1][1])))
    image=np.ma.masked_less_equal(t.a[r0:r1,c0:c1],t.nodata)
    offset=.5 if t.pixel_is_point else 0
    extent=[t.x0+(c0-offset)*t.dx,t.x0+(c1-offset)*t.dx,
            t.y0-(r1-offset)*t.dy,t.y0-(r0-offset)*t.dy]
    fig,ax=canvas(145)
    fig.subplots_adjust(right=.83,bottom=.14,top=.88)
    im=ax.imshow(image,extent=extent,origin='upper',cmap='Greys',vmin=float(image.min()),vmax=float(image.max()),
                 interpolation='nearest',aspect=1/np.cos(np.deg2rad(np.mean(ys))))
    cb=fig.colorbar(im,ax=ax,fraction=.05,pad=.04);cb.set_label('高程 / m')
    edges=set()
    for m in s['q3_missions']:
        route=['O01',*m['route'],'O01']
        edges.update(tuple(sorted((a,b))) for a,b in zip(route,route[1:]))
    for a,b in sorted(edges):
        ax.plot([nodes[a]['lon'],nodes[b]['lon']],[nodes[a]['lat'],nodes[b]['lat']],color=BLUE,lw=.65,alpha=.85)
    service=[n for n in nodes.values() if n['id']!='O01']
    ax.scatter([n['lon'] for n in service],[n['lat'] for n in service],s=20,c=BLUE,marker='o',label='服务区',zorder=4)
    ax.scatter(*zip(*sorted(sites)),s=28,c=ORANGE,marker='^',label='中继悬停位置',zorder=5)
    o=nodes['O01'];ax.scatter([o['lon']],[o['lat']],s=65,c='#111111',marker='*',label='调度中心 O01',zorder=6)
    ax.set(xlabel='经度 / °E',ylabel='纬度 / °N',title='第三问任务地形与航段投影')
    ax.ticklabel_format(useOffset=False,style='plain')
    fig.legend(*ax.get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.48,.98),ncol=3)
    finish(fig,ax,'01_terrain_routes',{'nodes':s['nodes'],'relay_sites':sorted(sites),'undirected_edges':sorted(edges),
                                   'dem_sha256':digest(DEM),'crop_pixels':[r0,r1,c0,c1],
                                   'display':'nearest pixel; grayscale linear; all mission geometry retained'},exclude=[cb.ax])


def payload(s):
    src=s['q1_safe_payload']['20'];zones=sorted(src);models=['A','B','C']
    a=np.array([[src[z][m] for m in models] for z in zones]);assert a.shape==(15,3)
    fig,ax=canvas(150);fig.subplots_adjust(left=.2,right=.82,bottom=.10,top=.92)
    im=ax.imshow(a,aspect='auto',cmap='Blues',vmin=0,vmax=float(a.max()),interpolation='nearest')
    ax.set_xticks(range(3),models);ax.set_yticks(range(15),zones)
    ax.set(xlabel='运输机型',ylabel='服务区',title='20% 返航余量下最大安全载荷')
    for (i,j),value in np.ndenumerate(a):
        ax.text(j,i,f'{value:.1f}',ha='center',va='center',color='white' if value>55 else '#111111',fontsize=8)
    cb=fig.colorbar(im,ax=ax,fraction=.065,pad=.06);cb.set_label('连续质量上界 / kg')
    finish(fig,ax,'02_safe_payload',{'zones':zones,'models':models,'kg':a.tolist(),'reserve':.2},exclude=[cb.ax])


def tradeoff(q2):
    front=q2['optimization']['pareto_candidates'];selected=q2['selected']['metrics']
    fig,ax=canvas()
    ax.scatter([x['metrics']['weighted_lateness_s']/3600 for x in front],
               [x['metrics']['energy_kwh'] for x in front],s=38,c='#8D9BA7',marker='o',label='非支配候选')
    ax.scatter([selected['weighted_lateness_s']/3600],[selected['energy_kwh']],s=110,c=BLUE,marker='*',label='选择方案',zorder=4)
    ax.set(xlabel='非医疗货箱加权迟到 / 加权小时',ylabel='运输能耗 / kWh',title='第二问有限搜索中的取舍')
    ax.legend(loc='upper left');ax.margins(.13)
    finish(fig,ax,'03_q2_tradeoff',{'candidates':[{k:v for k,v in x.items() if k!='missions'} for x in front],
                                'selected':selected,'x_unit_conversion':'weighted_lateness_s / 3600'})


def resources(events,name,title):
    kinds=['transport_craft','transport_battery','relay_craft','relay_component']
    prefixes={'transport_craft':'运输机','transport_battery':'电池','relay_craft':'中继机','relay_component':'组件'}
    rows=[(k,v) for k in kinds for v in sorted({e['resource'] for e in events if e['kind']==k})]
    index={row:i for i,row in enumerate(rows)}
    fig,ax=canvas(max(130,5*len(rows)+35));fig.subplots_adjust(left=.25,bottom=.10,top=.89,right=.97)
    for e in events:
        y=index[e['kind'],e['resource']];start=e['start_s']/3600;end=e['end_s']/3600
        active=e.get('return_s',e['end_s'])/3600
        ax.barh(y,active-start,left=start,height=.62,color=BLUE,edgecolor='none')
        if end>active:ax.barh(y,end-active,left=active,height=.62,color=GRAY,edgecolor='none')
    ax.set_yticks(range(len(rows)),[f'{prefixes[k]} {v}' for k,v in rows]);ax.invert_yaxis()
    ax.set(xlabel='任务起点后的时间 / h',title=title,xlim=(0,max(e['end_s'] for e in events)/3600*1.02))
    for i in range(1,len(rows)):
        if rows[i][0]!=rows[i-1][0]:ax.axhline(i-.5,color='#B8B8B8',lw=.5)
    active_label='作业占用（中继机含周转）' if any(e['kind']=='relay_craft' for e in events) else '作业占用'
    fig.legend(handles=[Patch(facecolor=BLUE,label=active_label),Patch(facecolor=GRAY,label='返航后充电')],
               loc='upper center',bbox_to_anchor=(.57,.99),ncol=2)
    finish(fig,ax,name,{'events':events,'rows':rows,'time_unit':'hour'})


def communication(s):
    records=s['q3_communication']['records'];missions=[m['id'] for m in s['q3_missions']]
    assert len(records)==283 and len(missions)==26
    fig,ax=canvas(175);fig.subplots_adjust(left=.17,bottom=.11,top=.89,right=.97)
    modes=sorted({r['mode'] for r in records})
    assert len(modes)==2,modes
    for r in records:
        direct=r['relay_id'] in ('',None)
        ax.barh(missions.index(r['mission']),(r['end_s']-r['start_s'])/3600,left=r['start_s']/3600,
                height=.68,color=BLUE if direct else ORANGE,edgecolor='none')
    ax.set_yticks(range(len(missions)),missions);ax.invert_yaxis()
    ax.set(xlabel='任务起点后的时间 / h',title='第三问名义通信保障',xlim=(0,max(r['end_s'] for r in records)/3600*1.02))
    fig.legend(handles=[Patch(facecolor=BLUE,label='直连'),Patch(facecolor=ORANGE,label='单跳中继')],
               loc='upper center',bbox_to_anchor=(.57,.98),ncol=2)
    finish(fig,ax,'06_communication',{'records':records,'time_unit':'hour','boundary_note':'See supplemental boundary guards; not resolved by this plot'})


def partition(s):
    q=s['q4']['solutions'];a=q['2']['balanced_resource_priority'];b=q['3']['balanced_resource_priority']
    keys=['A_craft','B_craft','C_craft','A_batteries','B_batteries','C_batteries','relay_craft','relay_components']
    labels=['A机','B机','C机','A电池','B电池','C电池','中继机','中继组件']
    data=[a['inventory'],a['total_required'],b['total_required']]
    fig,ax=canvas(115);xx=np.arange(len(keys))
    for i,(v,label,color) in enumerate(zip(data,['现有库存','两组需求','三组需求'],[GRAY,BLUE,ORANGE])):
        ax.bar(xx+(i-1)*.25,[v[k] for k in keys],width=.23,color=color,label=label)
    ax.set_xticks(xx,labels);ax.set_yticks(range(9));ax.set(ylabel='数量 / 架或组',title='分组独立执行的资源需求',ylim=(0,8.5))
    ax.legend(loc='upper left',ncol=3)
    finish(fig,ax,'07_q4_resources',{'resource_keys':keys,'inventory':data[0],'two_groups':data[1],'three_groups':data[2]})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--only',choices=[f'{n:02d}' for n in range(1,8)])
    args=parser.parse_args()
    s=read(ROOT/'交付材料'/'补充结果.json');q2=read(ROOT/'结果'/'q2_results.json')
    assert s['q2_missions']==q2['selected']['missions'],'stale supplement Q2'
    q3=read(ROOT/'结果'/'q3_solution.json');assert s['q3_missions']==q3['transport_missions'],'stale supplement Q3'
    assert s['q4']==read(ROOT/'结果'/'q4_results.json'),'stale supplement Q4'
    jobs=[lambda:terrain_map(s),lambda:payload(s),lambda:tradeoff(q2),
          lambda:resources(s['q2_resource_occupancy'],'04_q2_resources','第二问运输机与电池占用'),
          lambda:resources(s['q3_resource_occupancy'],'05_q3_resources','第三问运输与中继资源占用'),
          lambda:communication(s),lambda:partition(s)]
    for i,job in enumerate(jobs,1):
        if args.only is None or args.only==f'{i:02d}':job()
    sources=[ROOT/'交付材料'/'补充结果.json',ROOT/'结果'/'q2_results.json',ROOT/'结果'/'q3_solution.json',ROOT/'结果'/'q4_results.json',Path(__file__)]
    write(OUT/'provenance.json',{'backend':'Python / Matplotlib','matplotlib_version':matplotlib.__version__,
                              'font':'Microsoft YaHei','source_sha256':{str(p.relative_to(ROOT)):digest(p) for p in sources},
                              'figure_data_files':sorted(p.name for p in OUT.glob('*.data.json'))})


if __name__=='__main__':main()
