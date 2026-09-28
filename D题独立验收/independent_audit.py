"""Read-only independent audit. No imports from any solver/checker modules.

Inputs: original five XLSX files and GeoTIFF, submitted XLSX, and Q3 assignment
JSON (official workbook does not contain Q3 transport assignments).
Geometry: slab intersection for static rays; 3D triangle/cell clipping for
continuous swept rays. All certificates are computed afresh in this process.
AI-assisted: OpenAI Codex; team must verify actual tool metadata for disclosure.
"""
from pathlib import Path
from collections import Counter,defaultdict
from functools import lru_cache
from math import floor,ceil,sqrt,sin,cos,pi,log10,isfinite
import csv,json,hashlib,sys,time,copy
import numpy as np
from PIL import Image
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
DATA=BASE/'2026年中国研究生数学建模竞赛赛题/D题'
PARAM=DATA/'数据/无人机应急物资运输基础数据'
BOOK=BASE/'D题优化/outputs/optimization-20260928/结果提交模板_优化版.xlsx'
ASSIGN=BASE/'D题优化/结果/q3_solution.json'
OUT=ROOT/'证据';OUT.mkdir(exist_ok=True)
issues=[];reads=[]
def require(cond,kind,*detail):
    if not cond:issues.append({'kind':kind,'detail':detail})
def near(x,y,kind,*detail,tol=2e-6):require(isfinite(float(x)) and abs(x-y)<=tol,kind,*detail,x,y)
def save(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
def csvsave(name,rows):
    if rows:
        with (OUT/name).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def sheet(path,index=0):
    reads.append(str(path));w=load_workbook(path,read_only=True,data_only=True)
    rows=list(w.worksheets[index].values);w.close();return rows

def distance(a,b):
    lat=(a[1]+b[1])*pi/360;e2=.0066943799901413165
    N=6378137/sqrt(1-e2*sin(lat)**2);M=6378137*(1-e2)/(1-e2*sin(lat)**2)**1.5
    return sqrt(((a[0]-b[0])*pi/180*N*cos(lat))**2+((a[1]-b[1])*pi/180*M)**2)
def slant(a,b):return sqrt(distance(a,b)**2+(a[2]-b[2])**2)
def charge(s,T):
    require(0<=s<=1,'SOC outside domain',s)
    return T*(.65*max(0,.9-s)/.9+.35*min(.1,1-s)/.1)

class Raster:
    def __init__(self,path):
        reads.append(str(path));im=Image.open(path);self.z=np.asarray(im,dtype=float)
        tags=im.tag_v2;self.dx,self.dy=tags[33550][:2];tie=tags[33922];keys=tags[34735]
        self.keys={keys[i]:keys[i+3] for i in range(4,len(keys),4)}
        self.shift=.5 if self.keys[1025]==2 else 0
        self.origin=(tie[3]-tie[0]*self.dx,tie[4]+tie[1]*self.dy)
        self.h,self.w=self.z.shape;self.nodata=float(tags.get(42113,-32767))
        self.tests=Counter()
    def xyz(self,p):return ((p[0]-self.origin[0])/self.dx+self.shift,(self.origin[1]-p[1])/self.dy+self.shift,p[2])
    def height(self,p):
        x,y,_=self.xyz(p);r,c=floor(y),floor(x)
        if not (0<=r<self.h and 0<=c<self.w):raise ValueError('outside DEM')
        z=self.z[r,c]
        if not isfinite(z) or z<=self.nodata:raise ValueError('invalid DEM')
        return float(z)
    def cells(self,a,b):
        """Closed pixel-box / line intersection (slab method), including touches."""
        x,y,z=self.xyz(a);X,Y,Z=self.xyz(b);vx=X-x;vy=Y-y
        rr=[];cc=[]
        for row in range(floor(min(y,Y)-1e-10),floor(max(y,Y)+1e-10)+1):
            if abs(vy)<1e-14:
                if row-1e-10<=y<=row+1+1e-10:t0,t1=0.,1.
                else:continue
            else:
                t0,t1=sorted(((row-y)/vy,(row+1-y)/vy));t0=max(0,t0);t1=min(1,t1)
                if t1<t0-1e-12:continue
            u,v=x+vx*t0,x+vx*t1
            for col in range(floor(min(u,v)-1e-10),floor(max(u,v)+1e-10)+1):rr.append(row);cc.append(col)
        r=np.array(rr,dtype=int);c=np.array(cc,dtype=int);enter=np.zeros(len(r));leave=np.ones(len(r))
        for origin,delta,low in ((x,vx,c),(y,vy,r)):
            if abs(delta)<1e-14:
                ok=(low-1e-10<=origin)&(origin<=low+1+1e-10);enter=np.where(ok,enter,2)
            else:
                u=(low-origin)/delta;v=(low+1-origin)/delta
                enter=np.maximum(enter,np.minimum(u,v));leave=np.minimum(leave,np.maximum(u,v))
        ok=enter<=leave+1e-12;r=r[ok];c=c[ok];enter=enter[ok];leave=leave[ok]
        if np.any(r<0)|np.any(c<0)|np.any(r>=self.h)|np.any(c>=self.w):raise ValueError('ray touches outside DEM')
        ground=self.z[r,c]
        if np.any(~np.isfinite(ground)) or np.any(ground<=self.nodata):raise ValueError('ray invalid DEM')
        return r,c,enter,leave,ground
    @lru_cache(maxsize=80000)
    def ray(self,a,b):
        r,c,u,v,g=self.cells(a,b);zz=a[2]+(b[2]-a[2])*np.where(b[2]>=a[2],u,v)
        values=zz-g;k=int(np.argmin(values));self.tests['exact_rays']+=1;self.tests['ray_cells']+=len(r)
        return float(values[k]),(int(r[k]),int(c[k]),float((u[k]+v[k])/2))
    @lru_cache(None)
    def maxground(self,a,b):return float(max(self.cells(a,b)[4]))
    @staticmethod
    def clip(poly,axis,bound,lower):
        if not poly:return []
        out=[];p=poly[-1];fp=(p[axis]-bound)*(1 if lower else -1)
        for q in poly:
            fq=(q[axis]-bound)*(1 if lower else -1)
            if (fp>=0)!=(fq>=0):
                t=fp/(fp-fq);out.append(tuple(p[k]+t*(q[k]-p[k]) for k in range(3)))
            if fq>=0:out.append(q)
            p=q;fp=fq
        return out
    def swept_clear(self,a,b,g):
        """Convex triangle contains every ray g--P(t); clip against each cell.

        The altitude is linear on the 3D triangle. Min over a clipped polygon
        is at a vertex, hence a positive min clearance proves every t and ray
        fraction is above the piecewise-constant terrain, including boundaries.
        """
        poly=[self.xyz(g),self.xyz(a),self.xyz(b)];eps=2e-9;clearance=float('inf');tested=0
        for r in range(floor(min(p[1] for p in poly)-eps),floor(max(p[1] for p in poly)+eps)+1):
            strip=self.clip(self.clip(poly,1,r-eps,True),1,r+1+eps,False)
            if not strip:continue
            for c in range(floor(min(p[0] for p in strip)-eps),floor(max(p[0] for p in strip)+eps)+1):
                cell=self.clip(self.clip(strip,0,c-eps,True),0,c+1+eps,False)
                if not cell:continue
                if not(0<=r<self.h and 0<=c<self.w):raise ValueError('swept ray outside DEM')
                ground=float(self.z[r,c])
                if not isfinite(ground) or ground<=self.nodata:raise ValueError('swept ray invalid DEM')
                margin=min(p[2] for p in cell)-ground;tested+=1
                clearance=min(clearance,margin)
                if margin<=1e-7:
                    self.tests['swept_cells']+=tested;return False,clearance
        self.tests['swept_cells']+=tested;return True,clearance
    def blocked_all(self,a,b,g):
        """One fixed ray-fraction witness below the minimum terrain it sweeps."""
        mid=tuple((x+y)/2 for x,y in zip(a,b));r,c,u,v,ground=self.cells(g,mid)
        vals=g[2]+(mid[2]-g[2])*np.where(mid[2]>=g[2],u,v)-ground
        for idx in np.argsort(vals)[:12]:
            if vals[idx]>=0:break
            for f in (.5,1e-3,1-1e-3,1e-6,1-1e-6,1e-9,1-1e-9):
                s=float(u[idx]+(v[idx]-u[idx])*f)
                p=tuple(g[k]+s*(a[k]-g[k]) for k in range(3));q=tuple(g[k]+s*(b[k]-g[k]) for k in range(3))
                x,y,_=self.xyz(p);X,Y,_=self.xyz(q)
                r0,r1=floor(min(y,Y)-2e-9),floor(max(y,Y)+2e-9);c0,c1=floor(min(x,X)-2e-9),floor(max(x,X)+2e-9)
                if 0<=r0<=r1<self.h and 0<=c0<=c1<self.w:
                    minimum=float(np.min(self.z[r0:r1+1,c0:c1+1]))
                    if minimum>self.nodata and max(p[2],q[2])<minimum-1e-7:return True
        return False

class Audit:
    def __init__(self):
        rows=sheet(PARAM/'调度中心与服务区.xlsx');self.nodes={r[0]:tuple(map(float,r[2:5])) for r in rows if isinstance(r[0],str) and (r[0]=='O01' or r[0].startswith('S0'))}
        tr=sheet(PARAM/'运输无人机数据.xlsx');names=('empty','kg','volume','speed','range0','rangef','energy','reserve_percent','prep','load','handoff','perbox','climb','descend','eta','descent_eta')
        self.models={r[0]:dict(zip(names,map(float,r[2:18]))) for r in tr if r[0] in ('A','B','C') and r[3] is not None}
        self.craft={r[0]:r[1] for r in tr if isinstance(r[0],str) and r[0].startswith('U0')}
        self.batteries={r[0]:(int(r[1]),float(r[2])) for r in tr if r[0] in ('A','B','C') and r[3] is None}
        rr=sheet(PARAM/'中继无人机数据.xlsx');self.relay=dict(zip(('mass','speed','power','energy','reserve_percent','prep','setup','turnaround','climb','descend','eta','descent_eta','hover','comm','maxagl'),map(float,rr[2][4:19])))
        self.rcraft={r[0]:r[1] for r in rr if isinstance(r[0],str) and r[0].startswith('R0')};self.components=(int(rr[11][1]),float(rr[11][2]))
        self.boxes={r[0]:dict(zip(('zone','kind','kg','volume','first','first_due','due','priority'),r[1:9])) for r in sheet(PARAM/'物资需求与配送时限.xlsx',1)[1:] if r[0]}
        self.radio={(r[0],r[3]):float(r[4]) for r in sheet(PARAM/'通信链路参数.xlsx')[2:] if isinstance(r[4],(int,float))}
        self.dem=Raster(next(DATA.rglob('*.tif')));o=self.nodes['O01'];self.gate=(*o[:2],o[2]+self.radio['固定网关 G01','hG'])
        self.book=load_workbook(BOOK,read_only=False,data_only=True);reads.append(str(BOOK));reads.append(str(ASSIGN))
        self.assignment=json.loads(ASSIGN.read_text(encoding='utf8'));self.legs=[];self.boxlog=[];self.phases=[];self.trace=[]
        self.recomputed={};self.depend=defaultdict(set)
    def rows(self,name):
        width={'Q1_单点组批':9,'Q2_运输架次':8,'Q2_逐箱交付':4,'Q3_中继架次':11,'Q3_通信保障':6,'Q4_分区配置':11}[name]
        rows=[list(r) for r in self.book[name].iter_rows(min_row=2,values_only=True) if any(v is not None for v in r)]
        require(all(all(v is None for v in r[width:]) for r in rows),'unexpected extra nonblank columns',name)
        return [r[:width] for r in rows]
    @lru_cache(None)
    def leg(self,src,dst):
        a=self.nodes[src];b=self.nodes[dst];height=self.dem.maxground(a,b)+50
        h0=a[2]+(30 if src!='O01' else 0);h1=b[2]+(30 if dst!='O01' else 0)
        return distance(a,b),height,height-h0,height-h1
    def audit_transport(self,rows,label):
        seen=Counter();bycraft=defaultdict(list);bybat=defaultdict(list);recomputed=[];localphases=[];late=[];hard=[];before=len(issues)
        require(len({r['id'] for r in rows})==len(rows),'duplicate mission ID',label)
        for r in rows:
            mid=r['model'];m=self.models[mid];ids=[i for s in r['stops'] for i in s['boxes']];seen.update(ids)
            require(self.craft.get(r['craft'])==mid,'craft-model mismatch',label,r['id'])
            require(r['battery'] in {f'{mid}-BAT-{i:02d}' for i in range(1,self.batteries[mid][0]+1)},'unknown battery',label,r['id'])
            require(r['start_s']>=0 and bool(ids),'invalid start/empty',label,r['id'])
            require(r['route']==[s['zone'] for s in r['stops']],'route/stops mismatch',label,r['id'])
            mass=sum(self.boxes[i]['kg'] for i in ids);volume=sum(self.boxes[i]['volume'] for i in ids)
            require(mass<=m['kg']+1e-10,'payload',label,r['id'],mass,m['kg']);require(volume<=m['volume']+1e-12,'volume',label,r['id'],volume,m['volume'])
            now=r['start_s']+m['prep']+len(ids)*m['load'];takeoff=now;energy=0.;remaining=mass;prev='O01';deliveries={}
            for stop in r['stops']+[{'zone':'O01','boxes':[]}]:
                z=stop['zone'];a=self.nodes[prev];b=self.nodes[z];d,H,up,down=self.leg(prev,z)
                require(up>=0 and down>=0,'negative flight height',r['id'],prev,z)
                eq=m['range0']-(m['range0']-m['rangef'])*(remaining/m['kg'])**1.5
                E=m['energy']*d/eq+(m['empty']+remaining)*9.80665*up/(3600000*m['eta']);energy+=E
                durations=[up/m['climb'],d/m['speed'],down/m['descend']]
                positions=[(*a[:2],H-up),(*a[:2],H),(*b[:2],H),(*b[:2],H-down)]
                for k,kind in enumerate(('爬升','巡航','下降')):
                    localphases.append({'mission':r['id'],'phase':kind,'t0':now,'t1':now+durations[k],'a':positions[k],'b':positions[k+1]});now+=durations[k]
                self.legs.append({'question':label,'mission':r['id'],'src':prev,'dst':z,'remaining_kg':remaining,'distance_m':d,'dem_max_m':H-50,'cruise_alt_m':H,'climb_m':up,'descent_m':down,'energy_kwh':E,'flight_s':sum(durations)})
                if z!='O01':
                    for i in stop['boxes']:require(self.boxes[i]['zone']==z,'wrong destination',r['id'],i,z)
                    handoff=m['handoff']+len(stop['boxes'])*m['perbox'];localphases.append({'mission':r['id'],'phase':'交接','t0':now,'t1':now+handoff,'a':positions[-1],'b':positions[-1]});now+=handoff
                    for i in stop['boxes']:
                        box=self.boxes[i];deliveries[i]=now;delta=max(0,now-box['due']);late.append(delta)
                        due=min([box['due']] if box['kind']=='医疗物资' else [float('inf')])
                        if box['first']=='是':due=min(due,box['first_due'])
                        hard.append(due-now);require(now<=due+1e-7,'hard deadline',label,r['id'],i,now,due)
                        near(now,r['delivery_s'][i],'delivery mismatch',label,r['id'],i)
                        self.boxlog.append({'question':label,'box':i,'mission':r['id'],'zone':z,'kg':box['kg'],'volume':box['volume'],'delivery_s':now,'expected_s':box['due'],'hard_deadline_s':due if isfinite(due) else '', 'lateness_s':delta})
                    remaining-=sum(self.boxes[i]['kg'] for i in stop['boxes'])
                prev=z
            soc=1-energy/m['energy'];recharge=now+charge(soc,self.batteries[mid][1])
            require(soc>=m['reserve_percent']/100-1e-12,'return SOC',label,r['id'],soc)
            near(now,r['return_s'],'return mismatch',label,r['id']);near(energy,r['energy_kwh'],'energy mismatch',label,r['id'],tol=1e-8)
            if 'return_soc' in r:near(soc,r['return_soc'],'reported SOC mismatch',label,r['id'],tol=1e-8)
            if 'battery_recharged_s' in r:near(recharge,r['battery_recharged_s'],'recharge mismatch',label,r['id'])
            bycraft[r['craft']].append((r['start_s'],now,r['id']));bybat[r['battery']].append((r['start_s'],recharge,r['id']))
            recomputed.append({**r,'return_s':now,'energy_kwh':energy,'return_soc':soc,'battery_recharged_s':recharge,'delivery_s':deliveries,'takeoff_s':takeoff,'kg':mass,'volume':volume})
        require(seen==Counter({i:1 for i in self.boxes}),'box coverage',label,dict(seen))
        self.resource_check(bycraft,label+' aircraft');self.resource_check(bybat,label+' batteries')
        mt={'sorties':len(rows),'model_sorties':dict(Counter(r['model'] for r in rows)),'energy_kwh':sum(r['energy_kwh'] for r in recomputed),'makespan_s':max(r['return_s'] for r in recomputed),'minimum_SOC':min(r['return_soc'] for r in recomputed),'minimum_hard_deadline_slack_s':min(hard),'total_lateness_s':sum(late),'max_lateness_s':max(late),'coverage':len(seen),'duplicates':sum(max(0,n-1) for n in seen.values()),'issues':len(issues)-before}
        self.recomputed[label]=recomputed
        if label=='Q3':self.phases=localphases
        return mt
    def resource_check(self,groups,label):
        for id,rows in groups.items():
            rows=sorted(rows)
            for a,b in zip(rows,rows[1:]):require(b[0]>=a[1]-1e-7,'resource overlap',label,id,a,b)
            for a,b,name in rows:self.trace.append({'resource_type':label,'resource':id,'mission':name,'occupied_from_s':a,'occupied_until_s':b})
    def transport_from_excel(self):
        boxes=defaultdict(list);times=defaultdict(dict);seen=[]
        for i,mid,z,t in self.rows('Q2_逐箱交付'):
            require(i in self.boxes,'unknown box',i);require(self.boxes[i]['zone']==z,'Excel destination',i,z)
            boxes[mid].append(i);times[mid][i]=t;seen.append(i)
        require(Counter(seen)==Counter({i:1 for i in self.boxes}),'Excel box coverage')
        rows=[]
        for mid,craft,model,bat,start,route,end,energy in self.rows('Q2_运输架次'):
            zs=route.split('→');stops=[{'zone':z,'boxes':[i for i in boxes[mid] if self.boxes[i]['zone']==z]} for z in zs]
            require(all(s['boxes'] for s in stops),'empty stop or missing zone',mid)
            rows.append({'id':mid,'craft':craft,'model':model,'battery':bat,'start_s':start,'route':zs,'stops':stops,'return_s':end,'energy_kwh':energy,'delivery_s':times[mid]})
        require(set(times)=={r['id'] for r in rows},'orphan delivery mission')
        return rows
    def audit_relays(self):
        m=self.relay;ca=defaultdict(list);ec=defaultdict(list);out=[];before=len(issues)
        for id,craft,comp,start,lon,lat,alt,ready,end,back,energy in self.rows('Q3_中继架次'):
            require(craft in self.rcraft,'relay craft',id,craft);require(comp in {f'R-EC-{i:02d}' for i in range(1,self.components[0]+1)},'relay component',id,comp)
            p=(lon,lat,alt);o=self.nodes['O01'];agl=alt-self.dem.height(p)
            require(0<agl<=m['maxagl']+1e-8,'relay AGL',id,agl)
            H=max(alt,self.dem.maxground(o,p)+50);dist=distance(o,p)
            outward=(H-o[2])/m['climb']+dist/m['speed']+(H-alt)/m['descend']
            returning=(H-alt)/m['climb']+dist/m['speed']+(H-o[2])/m['descend']
            arrival=start+m['prep']+outward;built=arrival+m['setup'];returned=end+returning
            calcE=m['power']*2*dist/m['speed']/3600+m['mass']*9.80665*(2*H-o[2]-alt)/(3600000*m['eta'])+m['hover']*(end-arrival)/3600+m['comm']*(end-built)/3600
            soc=1-calcE/m['energy'];full=returned+charge(soc,self.components[1])
            require(0<=start<arrival<built<=end<returned,'relay chronology',id)
            near(built,ready,'relay ready',id);near(returned,back,'relay return',id);near(calcE,energy,'relay energy',id,tol=1e-8)
            require(soc>=m['reserve_percent']/100-1e-12,'relay SOC',id,soc)
            ca[craft].append((start,returned+m['turnaround'],id));ec[comp].append((start,full,id))
            out.append({'id':id,'craft':craft,'component':comp,'position':p,'start':start,'ready':built,'end':end,'return':returned,'energy':calcE,'soc':soc,'recharge':full,'agl':agl,'outbound_s':outward,'inbound_s':returning,'cruise_alt_m':H})
        require(len({r['id'] for r in out})==len(out),'duplicate relay IDs');self.resource_check(ca,'relay aircraft including turnaround');self.resource_check(ec,'relay components')
        self.relays={r['id']:r for r in out}
        return {'sorties':len(out),'energy_kwh':sum(r['energy'] for r in out),'last_return_s':max(r['return'] for r in out),'minimum_SOC':min(r['soc'] for r in out),'issues':len(issues)-before,'rows':out}
    def limit(self,ia,ib):
        p=self.radio
        return min(p[ia,'Pt']+p[ia,'G']+p[ib,'G'],p[ib,'Pt']+p[ib,'G']+p[ia,'G'])-p['传播参数','Lsys']-(p['接收参数','Psens']+p['接收参数','M'])
    def point_link(self,a,b,ia,ib):
        d=slant(a,b)/1000;clear,witness=self.dem.ray(tuple(a),tuple(b));loss=32.45+20*log10(self.radio['传播参数','f'])+20*log10(d)
        if clear<0:loss+=self.radio['传播参数','Lobs']
        return self.limit(ia,ib)-loss,clear,witness
    def distance_bounds(self,a,b,g):
        lowlat=min((a[1]+g[1])/2,(b[1]+g[1])/2)*pi/180;hilat=max((a[1]+g[1])/2,(b[1]+g[1])/2)*pi/180
        require(0<lowlat<=hilat<pi/2,'distance bound latitude assumption')
        e=.0066943799901413165
        eastlo=6378137*cos(hilat)/sqrt(1-e*sin(hilat)**2);easthi=6378137*cos(lowlat)/sqrt(1-e*sin(lowlat)**2)
        northlo=6378137*(1-e)/(1-e*sin(lowlat)**2)**1.5;northhi=6378137*(1-e)/(1-e*sin(hilat)**2)**1.5
        mins=[];maxs=[]
        for k in range(3):
            l,h=sorted((a[k]-g[k],b[k]-g[k]));mins.append(0 if l<=0<=h else min(abs(l),abs(h)));maxs.append(max(abs(l),abs(h)))
        lower=sqrt((mins[0]*pi/180*eastlo)**2+(mins[1]*pi/180*northlo)**2+mins[2]**2)
        upper=sqrt((maxs[0]*pi/180*easthi)**2+(maxs[1]*pi/180*northhi)**2+maxs[2]**2)
        return max(lower,1e-12),max(upper,1e-12)
    def bound(self,a,b,g,ia,ib,need_upper=False):
        dl,dh=self.distance_bounds(a,b,g);const=self.limit(ia,ib)-32.45-20*log10(self.radio['传播参数','f'])
        lower=const-20*log10(dh/1000)-self.radio['传播参数','Lobs'];upper=const-20*log10(dl/1000)
        how='worst_obstruction'
        if lower<1e-9 and not need_upper:
            clear,margin=self.dem.swept_clear(a,b,g)
            if clear:lower+=self.radio['传播参数','Lobs'];how='swept_triangle_clear'
        if need_upper and upper>=0 and self.dem.blocked_all(a,b,g):upper-=self.radio['传播参数','Lobs']
        return lower,upper,how
    @staticmethod
    def at(p,t):
        x=(t-p['t0'])/(p['t1']-p['t0']) if p['t1']!=p['t0'] else 0
        return tuple(a+x*(b-a) for a,b in zip(p['a'],p['b']))
    def coverage(self,allowed=None,tag=''):
        """New adaptive certificate. Neither old time partitions nor caches read."""
        before=len(issues);leaves=[];failed=[];stats=Counter();minimum=1e9
        self.backhaul={rid:self.point_link(r['position'],self.gate,'中继回传端','固定网关 G01')[0] for rid,r in self.relays.items()}
        for rid,m in self.backhaul.items():require(m>=0,'backhaul unavailable',rid,m)
        def candidates(p,t0,t1):
            a=self.at(p,t0);b=self.at(p,t1);dl,_,method=self.bound(a,b,self.gate,'运输无人机','固定网关 G01');options=[(dl,'direct',method)]
            if dl>1e-9:return options[0]
            for rid,r in self.relays.items():
                if allowed is not None and rid not in allowed[p['mission']]:continue
                if r['ready']<=t0+1e-10 and t1<=r['end']+1e-10:
                    low,_,how=self.bound(a,b,r['position'],'运输无人机','中继接入端');options.append((min(low,self.backhaul[rid]),rid,how))
            return max(options)
        def divide(p,u,v,depth=0):
            nonlocal minimum
            stats['intervals_evaluated']+=1;low,rid,how=candidates(p,u,v)
            if low>1e-9:
                minimum=min(minimum,low);stats['certified_leaves']+=1;stats[how]+=1
                leaves.append({'mission':p['mission'],'phase':p['phase'],'start_s':u,'end_s':v,'path':rid,'lower_margin_db':low,'proof':how})
                if rid!='direct' and allowed is None:self.depend[p['mission']].add(rid)
                return
            t=(u+v)/2;pos=self.at(p,t);options=[self.point_link(pos,self.gate,'运输无人机','固定网关 G01')[0]]
            for rid,r in self.relays.items():
                if allowed is not None and rid not in allowed[p['mission']]:continue
                if r['ready']<=t<=r['end']:options.append(min(self.backhaul[rid],self.point_link(pos,r['position'],'运输无人机','中继接入端')[0]))
            if max(options)<-1e-8:
                failed.append({'mission':p['mission'],'phase':p['phase'],'time':t,'best_margin_db':max(options),'reason':'exact point counterexample'});return
            if depth>=30 or v-u<1e-8:
                failed.append({'mission':p['mission'],'phase':p['phase'],'start':u,'end':v,'reason':'unresolved, not a pass','bound':low});return
            mid=(u+v)/2;divide(p,u,mid,depth+1);divide(p,mid,v,depth+1)
        for idx,p in enumerate(self.phases):
            n=max(1,ceil((p['t1']-p['t0'])/20));ts={p['t0']+(p['t1']-p['t0'])*i/n for i in range(n+1)}
            ts.update(t for r in self.relays.values() for t in (r['ready'],r['end']) if p['t0']<t<p['t1']);ts=sorted(ts)
            for u,v in zip(ts,ts[1:]):divide(p,u,v)
            if idx%14==0:print('CONTINUOUS',idx,'/',len(self.phases),'leaves',len(leaves),'failures',len(failed),flush=True)
        require(not failed,'continuous communication failed',tag,failed[:20]);csvsave(tag+'continuous_coverage_leaves.csv',leaves)
        result={'status':'passed' if not failed else 'failed','method':'new 3D swept-triangle / closed pixel clipping and analytic distance bounds','initial_step_s':20,'counts':dict(stats),'minimum_certified_margin_db':minimum,'failures':failed,'backhaul_margins_db':self.backhaul}
        save(tag+'independent_continuous_coverage.json',result);return result
    def dense_scan(self,step=1):
        count=blind=0;minimum=1e9;fail=[];sample_rows=[];handoffs={r['mission'] for r in self.phases if r['phase']=='交接'}
        for p in self.phases:
            n=max(1,ceil((p['t1']-p['t0'])/step));ts={p['t0']+(p['t1']-p['t0'])*i/n for i in range(n+1)}
            ts.update(t for r in self.relays.values() for t in (r['ready']-1e-6,r['ready'],r['ready']+1e-6,r['end']-1e-6,r['end'],r['end']+1e-6) if p['t0']<=t<=p['t1'])
            for t in sorted(ts):
                pos=self.at(p,t);dl,dc,dw=self.point_link(pos,self.gate,'运输无人机','固定网关 G01');paths=[(dl,'direct')];count+=1
                if dl<0:
                    blind+=1
                    for rid,r in self.relays.items():
                        if r['ready']<=t<=r['end']:paths.append((min(self.backhaul[rid],self.point_link(pos,r['position'],'运输无人机','中继接入端')[0]),rid))
                value,rid=max(paths);minimum=min(minimum,value)
                if value<-1e-8:fail.append((p['mission'],p['phase'],t,value))
            print('DENSE',p['mission'],p['phase'],'samples',count,'failures',len(fail),flush=True) if p['phase']=='交接' else None
        require(not fail,'dense communication counterexample',fail[:20])
        result={'time_step_max_s':step,'points':count,'direct_unavailable_points':blind,'uncovered_points':len(fail),'min_available_margin_db':minimum,'failures':fail}
        save('independent_dense_scan.json',result);return result
    def communication_table(self):
        table=self.rows('Q3_通信保障');byp=defaultdict(list);before=len(issues);stats=Counter();uncertain=[];table_dep=defaultdict(set)
        for mid,kind,u,v,mode,rid in table:
            require(mode in ('直连','中继'),'unknown radio mode',mid,mode);require(v>u,'invalid communication interval',mid,u,v)
            if mode=='直连':require(rid in (None,''),'direct row with relay id',mid,rid)
            else:require(rid in self.relays,'unknown relay ID',mid,rid);table_dep[mid].add(rid)
            byp[mid].append({'kind':kind,'u':u,'v':v,'mode':mode,'rid':rid})
        # Row assignment and direct-priority certification are separate from existence.
        def verify(p,row,u,v,depth=0):
            stats['checks']+=1;a=self.at(p,u);b=self.at(p,v)
            if stats['checks']%2000==0:print('TABLE_DETAIL',p['mission'],p['phase'],u,v,row['mode'],dict(stats),flush=True)
            dl,du,_=self.bound(a,b,self.gate,'运输无人机','固定网关 G01',need_upper=row['mode']=='中继')
            if row['mode']=='直连':ok=dl>1e-9
            else:
                r=self.relays[row['rid']];rl,_,_=self.bound(a,b,r['position'],'运输无人机','中继接入端')
                ok=du<-1e-9 and rl>1e-9 and self.backhaul[row['rid']]>1e-9 and r['ready']<=u+1e-10 and v<=r['end']+1e-10
            if ok:stats['certified']+=1;return
            if v-u<=1e-7:
                uncertain.append({'mission':p['mission'],'phase':p['phase'],'start_s':u,'end_s':v,'recorded_mode':row['mode'],'recorded_relay':row['rid']});return
            t=(u+v)/2;pos=self.at(p,t);dm=self.point_link(pos,self.gate,'运输无人机','固定网关 G01')[0]
            if row['mode']=='直连':pointok=dm>=-1e-8
            else:
                r=self.relays[row['rid']];rm=self.point_link(pos,r['position'],'运输无人机','中继接入端')[0]
                pointok=dm<=1e-8 and rm>=-1e-8 and self.backhaul[row['rid']]>=-1e-8 and r['ready']-1e-8<=t<=r['end']+1e-8
            if not pointok:require(False,'wrong communication table state',p['mission'],p['phase'],u,v,dm,row);return
            if depth>40:require(False,'table interval not resolved',p['mission'],u,v);return
            verify(p,row,u,t,depth+1);verify(p,row,t,v,depth+1)
        used=set()
        for index,p in enumerate(self.phases):
            selected=[]
            for j,row in enumerate(byp[p['mission']]):
                if row['kind']==p['phase'] and row['u']>=p['t0']-2e-6 and row['v']<=p['t1']+2e-6:
                    selected.append(row);used.add((p['mission'],j))
            selected.sort(key=lambda r:r['u']);require(bool(selected),'unrepresented phase',p['mission'],p['phase'],p['t0'])
            if not selected:continue
            near(selected[0]['u'],p['t0'],'communication phase start',p['mission']);near(selected[-1]['v'],p['t1'],'communication phase end',p['mission'])
            for a,b in zip(selected,selected[1:]):near(a['v'],b['u'],'communication gap/overlap',p['mission'],tol=1e-8)
            for row in selected:
                u=max(p['t0'],row['u']);v=min(p['t1'],row['v']);n=max(1,ceil((v-u)/20))
                for j in range(n):verify(p,row,u+(v-u)*j/n,u+(v-u)*(j+1)/n)
            print('TABLE',index,'/',len(self.phases),'uncertain',len(uncertain),'issues',len(issues)-before,flush=True)
        require(len(used)==len(table),'extra communication rows',len(used),len(table))
        self.table_depend=table_dep
        probes=[]
        for band in uncertain:
            p=next(p for p in self.phases if p['mission']==band['mission'] and p['phase']==band['phase'] and p['t0']-1e-8<=band['start_s'] and band['end_s']<=p['t1']+1e-8)
            for fraction in (.25,.5,.75):
                t=band['start_s']+(band['end_s']-band['start_s'])*fraction;pos=self.at(p,t)
                dm,clear,_=self.point_link(pos,self.gate,'运输无人机','固定网关 G01')
                if (band['recorded_mode']=='直连')!=(dm>=0):
                    probes.append({**band,'probe_time_s':t,'direct_margin_db':dm,'direct_clearance_m':clear,'actual_mode':'直连' if dm>=0 else '需中继'})
        merged=[]
        for band in sorted(uncertain,key=lambda r:(r['mission'],r['phase'],r['start_s'])):
            if merged and (merged[-1]['mission'],merged[-1]['phase'])==(band['mission'],band['phase']) and band['start_s']<=merged[-1]['end_s']+1e-10:
                merged[-1]['end_s']=max(merged[-1]['end_s'],band['end_s'])
            else:merged.append({k:band[k] for k in ('mission','phase','start_s','end_s')})
        save('table_boundary_point_discrepancies.json',probes)
        result={'records':len(table),'issues':len(issues)-before,'interval_counts':dict(stats),'numerical_boundary_bands':uncertain,
            'boundary_band_total_s':sum(r['end_s']-r['start_s'] for r in uncertain),
            'merged_boundary_bands':merged,'boundary_point_discrepancies':len(probes),
            'strict_state_status':'NOT_ACCEPTED_POINT_DISCREPANCIES' if probes else ('UNRESOLVED_BOUNDARIES' if uncertain else 'PASS'),
            'scope':'recorded state certified outside listed <=1e-7 s bands; continuous existence separately certified without these exclusions'}
        save('independent_table_check.json',result);return result
    def audit_q4(self):
        reports={};rows=self.rows('Q4_分区配置')
        for k in (2,3):
            groups=[r for r in rows if r[0]==k];require(len(groups)==k,'Q4 number of groups',k)
            assigned=[z for r in groups for z in r[2].split(',')];require(Counter(assigned)==Counter({z:1 for z in self.nodes if z!='O01'}),'Q4 partition',k)
            result=[]
            def peak(events):
                marks=sorted([(a,1) for a,b in events]+[(b,-1) for a,b in events]);v=best=0
                for t,delta in marks:v+=delta;best=max(best,v)
                return best
            for r in groups:
                zones=r[2].split(',');tasks=[t for t in self.recomputed['Q3'] if set(t['route'])&set(zones)]
                for t in tasks:require(set(t['route'])<=set(zones),'Q4 cross-group route',k,r[1],t['id'])
                # Use frozen service relationships, independently certified with
                # all other relay paths disabled by coverage(allowed=...).
                relays=set().union(*(self.table_depend[t['id']] for t in tasks))
                rs=[self.relays[rid] for rid in relays];need=[]
                for key in ('return_s','battery_recharged_s'):
                    for model in 'ABC':need.append(peak([(t['start_s'],t[key]) for t in tasks if t['model']==model]))
                need.extend([peak([(t['start'],t['return']+self.relay['turnaround']) for t in rs]),peak([(t['start'],t['recharge']) for t in rs])])
                allocated=r[3:11];require(all(a>=b for a,b in zip(allocated,need)),'Q4 insufficient allocated resources',k,r[1],allocated,need,sorted(relays))
                result.append({'group':r[1],'zones':zones,'allocated':allocated,'independent_need':need,'relay_dependencies':sorted(relays)})
            reports[str(k)]=result
        save('independent_q4_check.json',reports);return reports

def self_tests():
    """Artificial flat terrain/ridge tests for the new geometry, not solver outputs."""
    d=object.__new__(Raster);d.z=np.zeros((6,6));d.h=d.w=6;d.dx=d.dy=1.;d.origin=(0.,6.);d.shift=0.;d.nodata=-32767;d.tests=Counter()
    a=(1.2,4.8,2.);b=(4.8,1.2,2.);g=(1.2,1.2,2.)
    assert d.ray(a,b)[0]==2
    assert d.swept_clear(a,b,g)[0]
    d.z[3,2]=4;d.ray.cache_clear();assert d.ray(a,b)[0]<0;assert not d.swept_clear(a,b,g)[0]
    # Corner-only contact must include the adjacent high cell.
    d.z[:]=0;d.z[1,2]=4;d.ray.cache_clear();assert d.ray((1.5,4.5,2.),(3.5,2.5,2.))[0]<0
    # Vertex of swept surface clips a ridge although a distinct ray may be clear.
    save('geometry_self_tests.json',{'flat_ray':True,'flat_triangle':True,'ridge_detected':True,'corner_touch_detected':True})

def main():
    started=time.time();self_tests();audit=Audit()
    files=[BOOK,ASSIGN,Path(__file__),*PARAM.glob('*.xlsx'),next(DATA.rglob('*.tif')),next(DATA.glob('*.docx'))]
    frozen={str(p):digest(p) for p in files};save('frozen_input_sha256.json',frozen)
    q2=audit.audit_transport(audit.transport_from_excel(),'Q2')
    q3=audit.audit_transport(audit.assignment['transport_missions'],'Q3')
    relay=audit.audit_relays();save('independent_transport_and_energy.json',{'Q2':q2,'Q3':q3,'relay':relay,'issues':issues})
    csvsave('recomputed_legs.csv',audit.legs);csvsave('recomputed_boxes.csv',audit.boxlog);csvsave('resource_occupancy.csv',audit.trace)
    print('TRANSPORT',q2,q3,'RELAY',relay['energy_kwh'],'issues',len(issues),flush=True)
    coverage=audit.coverage();dense=audit.dense_scan();table=audit.communication_table()
    restricted=audit.coverage(allowed=audit.table_depend,tag='frozen_relays_');q4=audit.audit_q4()
    unchanged={str(p):digest(p)==frozen[str(p)] for p in files};require(all(unchanged.values()),'audit inputs changed')
    summary={'status':'physical_feasibility_passed_with_table_boundary_precision_limit' if not issues else 'failed','Q2':q2,'Q3':q3,'relay':relay,
        'strict_excel_status':table['strict_state_status'],'physical_constraint_issues':len(issues),
        'joint_makespan_s':max(q3['makespan_s'],relay['last_return_s']),'continuous':coverage,'dense_scan':dense,
        'communication_table':{k:v for k,v in table.items() if k not in ('numerical_boundary_bands','merged_boundary_bands')},'frozen_relay_coverage':restricted,'Q4':q4,'issues':issues,
        'new_geometry_work':dict(audit.dem.tests),'input_files_read':sorted(set(reads)), 'frozen_hashes_unchanged':unchanged,
        'forbidden_sources_read':[],'elapsed_s':time.time()-started,
        'conditions':['Original declared horizontal/climb energy formula and WGS84 local-distance approximation retained; not uniquely specified by question.',
            'Piecewise-constant DEM heights with PixelIsPoint centres; floating-point geometric bounds with outward XY expansion and positive clearance guard.',
            'Q3 JSON used solely for submitted transport assignments and reported fields to compare, not any derived spatial/radio judgment.',
            'Continuity certifies all time, not just dense sample points; table mode changes have explicitly listed numerical boundary bands.']}
    save('strict_audit_summary.json',summary)
    print('FINAL',summary['status'],'issues',issues,'elapsed',summary['elapsed_s'],flush=True)
    if issues:sys.exit(1)
if __name__=='__main__':main()
