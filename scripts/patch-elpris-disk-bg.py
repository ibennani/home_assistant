#!/usr/bin/env python3
"""Fix elpris apexcharts: restore midnight annotations + disk bg column series."""
import re
from pathlib import Path

DISK_DG = (
    "const ST=(typeof states!=='undefined'&&states)?states:hass.states;"
    "const stepMin=(Array.isArray(entity.attributes.today)&&entity.attributes.today.length>24)?15:60;"
    "const slotLen=stepMin;const slotMs=slotLen*60000;"
    "const vals=[];const pushArr=(a)=>{if(Array.isArray(a))a.forEach((v)=>{const f=parseFloat(v);if(!isNaN(f))vals.push(f);});};"
    "pushArr(entity.attributes.today);"
    "const tmOk=entity.attributes.tomorrow_valid===true||String(entity.attributes.tomorrow_valid).toLowerCase()==='true';"
    "if(tmOk)pushArr(entity.attributes.tomorrow);"
    "const n=vals.length;const out=[];if(n<4)return out;"
    "let maxY=0;vals.forEach((v)=>{if(v>maxY)maxY=v;});maxY=Math.round((maxY*1.12+0.05)*100)/100;"
    "const cfg={ecoMin:66,intMin:100,heavyPct:0.75,heavyW:1,lightW:0.5,priceThr:2,wkdMorn:6,wkdAft:16,wkdEnd:8};"
    "const floorSlot=(d)=>{const x=new Date(d);x.setSeconds(0,0);const m=x.getMinutes()%slotLen;if(m)x.setMinutes(x.getMinutes()-m);return x;};"
    "const now=new Date();const baseMidnight=new Date(now);baseMidnight.setHours(0,0,0,0);const baseTs=baseMidnight.getTime();"
    "const numSlots=(min)=>Math.ceil(min/slotLen);"
    "const heavyLight=(ns)=>{const nh=Math.ceil(ns*cfg.heavyPct);const nl=ns-nh;const tw=nh*cfg.heavyW+nl*cfg.lightW;return{nh,hf:cfg.heavyW/tw,lf:cfg.lightW/tw};};"
    "const wCost=(i,ns,nh,hf,lf)=>{if(i+ns>vals.length)return null;let hs=0,ls=0;for(let j=0;j<nh;j++)hs+=vals[i+j];for(let j=nh;j<ns;j++)ls+=vals[i+j];return hs*hf+ls*lf;};"
    "const nextDeadline=(cycleMin)=>{const cur=new Date(now);const fin=new Date(cur.getTime()+cycleMin*60000);const isWk=cur.getDay()>=1&&cur.getDay()<=5;"
    "const mk=(h)=>{const d=new Date(cur);d.setHours(h,0,0,0);return d;};"
    "if(isWk){const morning=mk(cfg.wkdMorn);const aft=mk(cfg.wkdAft);if(fin<=morning)return morning;if(fin<=aft)return aft;"
    "const nd=new Date(cur);nd.setDate(nd.getDate()+1);const ndWk=nd.getDay()>=1&&nd.getDay()<=5;nd.setHours(ndWk?cfg.wkdMorn:cfg.wkdEnd,0,0,0);return nd;}"
    "const td=mk(cfg.wkdEnd);if(fin<=td)return td;const nd=new Date(cur);nd.setDate(nd.getDate()+1);const ndWk=nd.getDay()>=1&&nd.getDay()<=5;"
    "nd.setHours(ndWk?cfg.wkdMorn:cfg.wkdEnd,0,0,0);return nd;};"
    "const bestRuns=(cycleMin)=>{const ns=numSlots(cycleMin);const deadline=nextDeadline(cycleMin);let first=floorSlot(now);"
    "if(first<now)first=new Date(first.getTime()+slotMs);const latestDt=new Date(deadline.getTime()-cycleMin*60000);const latest=floorSlot(latestDt);"
    "let fi=Math.ceil((first.getTime()-baseTs)/slotMs);let li=Math.floor((latest.getTime()-baseTs)/slotMs);const maxStart=n-ns;if(fi<0)fi=0;if(li>maxStart)li=maxStart;"
    "const{nh,hf,lf}=heavyLight(ns);let minC=null,bestI=-1;const costs=[];for(let i=fi;i<=li;i++){const c=wCost(i,ns,nh,hf,lf);costs[i]=c;if(c===null)continue;if(minC===null||c<minC){minC=c;bestI=i;}}"
    "return{ns,minC,bestI,costs,fi,li};};"
    "const avgRun=(bi,ns)=>{if(bi<0)return 999;let s=0;for(let k=0;k<ns;k++)s+=vals[bi+k];return s/ns;};"
    "const eco=bestRuns(cfg.ecoMin);const int=bestRuns(cfg.intMin);const useInt=int.bestI>=0&&avgRun(int.bestI,int.ns)<cfg.priceThr;const pick=useInt?int:eco;"
    "const marked=new Array(n).fill(false);"
    "const vantar=ST['input_boolean.diskmaskin_fjarrstart_vantar']?.state==='on';"
    "if(vantar){const startRaw=ST['input_text.diskmaskin_tid_fjarrstart']?.state||'';const prog=ST['input_text.diskmaskin_program_fjarrstart']?.state||'';"
    "const dur=prog.indexOf('Intensiv70')>=0?cfg.intMin:cfg.ecoMin;const start=startRaw?new Date(startRaw.replace(' ','T')):null;"
    "if(start&&!isNaN(start.getTime())){const bi=Math.round((start.getTime()-baseTs)/slotMs);const ns=numSlots(dur);for(let j=0;j<ns;j++)if(bi+j>=0&&bi+j<n)marked[bi+j]=true;}}"
    "else if(pick.minC!==null){const thr=pick.minC*1.02+1e-9;for(let i=pick.fi;i<=pick.li;i++){const c=pick.costs[i];if(c!==undefined&&c!==null&&c<=thr){for(let j=0;j<pick.ns;j++)if(i+j<n)marked[i+j]=true;}}}"
    "for(let i=0;i<n;i++){if(!marked[i])continue;const x=baseTs+i*slotMs;out.push({x,y:maxY,fillColor:'rgba(42,107,79,0.28)'});}return out;"
)

MIDNIGHT_10 = """          annotations:
            xaxis:
            - x: EVAL:new Date(new Date().setHours(24, 0, 0, 0))
              borderColor: '#ff4081'
              strokeDashArray: 0
              label:
                text: Midnatt
                style:
                  color: '#ffffff'
                  background: '#ff4081'"""

MIDNIGHT_8 = """        annotations:
          xaxis:
          - x: EVAL:new Date(new Date().setHours(24, 0, 0, 0))
            borderColor: '#ff4081'
            strokeDashArray: 0
            label:
              text: Midnatt
              style:
                color: '#ffffff'
                background: '#ff4081'"""

DISK_SERIES_8 = f"""        - entity: sensor.elpris_marginal_kwh_se3
          name: Diskfönster
          type: column
          stack_group: disk_bg
          data_generator: "{DISK_DG}"
          show:
            legend_value: false
            in_legend: false
            in_header: false
            in_chart: true
            extremas: false
            datalabels: false
            tooltip: false
"""

DISK_SERIES_6 = DISK_SERIES_8.replace("        ", "      ")

PAT_10 = re.compile(
    r"          annotations:\n            xaxis: \"EVAL:\(\) => \{.*?\}\n\"(?=\n          grid:)",
    re.DOTALL,
)
PAT_8 = re.compile(
    r"        annotations:\n          xaxis: \"EVAL:\(\) => \{.*?\}\n\"(?=\n        grid:)",
    re.DOTALL,
)


def patch(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text, n1 = PAT_10.subn(MIDNIGHT_10, text)
    text, n2 = PAT_8.subn(MIDNIGHT_8, text)
    if n1 + n2 == 0 and "xaxis: \"EVAL:" in text:
        raise SystemExit("EVAL annotation blocks remain but pattern did not match")

    if "name: Diskfönster" not in text:
        text = text.replace(
            "        series:\n        - entity: sensor.elpris_marginal_kwh_se3\n          name: Nu",
            "        series:\n" + DISK_SERIES_8 + "        - entity: sensor.elpris_marginal_kwh_se3\n          name: Nu",
            1,
        )
        text = text.replace(
            "      series:\n      - entity: sensor.elpris_marginal_kwh_se3\n        name: Nu",
            "      series:\n" + DISK_SERIES_6 + "      - entity: sensor.elpris_marginal_kwh_se3\n        name: Nu",
            1,
        )

    path.write_text(text, encoding="utf-8")
    print(f"Patched {path} (annotations: {n1}+{n2})")


if __name__ == "__main__":
    patch(Path(__file__).resolve().parents[1] / "dashboards" / "dashboard-september-2025.yaml")
