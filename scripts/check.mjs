#!/usr/bin/env node
// Audit actual cutout handoffs; uniform sampling can miss sub-second preludes.
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
const args=process.argv.slice(2);
const pi=args.indexOf('--project');
const project=path.resolve(pi<0?'.':args[pi+1]);
if(pi>=0)args.splice(pi,2);
const job=JSON.parse(fs.readFileSync(path.join(project,'job.resolved.json'),'utf8'));
const fps=job.fps||30;let time=0;const times=[0];
for(let i=0;i<job.scenes.length;i++){
  const s=job.scenes[i];
  if(i>0&&s.cutout){const lead=Math.min(s.leadIn??.25,job.scenes[i-1].duration);times.push(time-lead*.5);}
  times.push(time+Math.min(s.duration*.3,1/fps));
  time+=s.duration;
}
if(job.endCard){times.push(time+Math.min(.15,job.endCard.duration*.5));time+=job.endCard.duration;}
times.push(time-1/fps);
const at=[...new Set(times.filter(t=>t>=0&&t<time).map(t=>Math.round(t*1e5)/1e5))].sort((a,b)=>a-b);
const childArgs=['--yes','hyperframes@0.8.127','check',project,...args];
if(!args.includes('--at')&&job.style==='cutout-reveal')childArgs.push('--at',at.join(','));
const result=spawnSync(process.platform==='win32'?'npx.cmd':'npx',childArgs,{stdio:'inherit',shell:false});
if(result.error){console.error(result.error.message);process.exit(1);}
process.exit(result.status??1);
